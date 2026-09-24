import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.academic import ClassDivision, Enrollment, Lecture
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.user import ProfessorProfile, StudentProfile, User
from app.models.verification import (
    ClassroomVerification,
    ClassroomVerificationResult,
    DetectionStatus,
    DiscrepancyType,
    StudentReferencePhoto,
    VerificationDecision,
    VerificationDecisionAction,
    VerificationStatus,
)
from app.schemas.verification import (
    ClassroomVerificationDetailOut,
    ClassroomVerificationOut,
    VerificationDecisionOut,
    VerificationDecisionRequest,
    VerificationResultOut,
)
from app.services import violation_service
from app.services.attendance_service import PRESENT_LIKE
from app.services.verification.provider import StudentReference, VisionProvider

settings = get_settings()
logger = logging.getLogger("proxybusters.verification")

PROVIDER_NAME = "anthropic_claude_vision"

# Discrepancy types a professor may actually act on, and which actions are valid for each.
# Enforced here (not just in the UI) — AI evidence alone never touches attendance state; the
# only door into that is a professor decision through one of these two paths.
ALLOWED_ACTIONS: dict[DiscrepancyType, set[VerificationDecisionAction]] = {
    DiscrepancyType.ATTENDED_NOT_DETECTED: {
        VerificationDecisionAction.CONFIRMED_PRESENT,
        VerificationDecisionAction.VIOLATION,
    },
    DiscrepancyType.DETECTED_NOT_ATTENDED: {
        VerificationDecisionAction.ASKED_TO_SCAN,
        VerificationDecisionAction.DISMISSED,
    },
}


def _get_provider() -> VisionProvider:
    # Local import: keeps the `anthropic` SDK optional to import until a verification is
    # actually run, and gives tests a single seam to monkeypatch (see test_classroom_verification.py).
    from app.services.verification.anthropic_provider import AnthropicVisionProvider

    return AnthropicVisionProvider()


def _bucket_confidence(confidence: float) -> DetectionStatus:
    if confidence >= settings.ai_confidence_confirmed:
        return DetectionStatus.CONFIRMED
    if confidence >= settings.ai_confidence_high:
        return DetectionStatus.HIGH_CONFIDENCE
    if confidence <= 0.05:
        return DetectionStatus.NOT_DETECTED
    return DetectionStatus.UNCERTAIN


def _classify(qr_present: bool, ai_status: DetectionStatus) -> DiscrepancyType:
    detected = ai_status in (DetectionStatus.CONFIRMED, DetectionStatus.HIGH_CONFIDENCE)
    if qr_present and detected:
        return DiscrepancyType.ATTENDED_AND_DETECTED
    if qr_present and not detected:
        return DiscrepancyType.ATTENDED_NOT_DETECTED
    if not qr_present and detected:
        return DiscrepancyType.DETECTED_NOT_ATTENDED
    return DiscrepancyType.NONE


def start_verification(
    db: Session,
    professor_profile: ProfessorProfile,
    session_obj: AttendanceSession,
    images: list[tuple[bytes, str]],
) -> ClassroomVerification:
    verification = ClassroomVerification(
        session_id=session_obj.id,
        lecture_id=session_obj.lecture_id,
        professor_id=professor_profile.id,
        status=VerificationStatus.PROCESSING,
        image_count=len(images),
        provider=PROVIDER_NAME,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification


def run_verification_job(verification_id: uuid.UUID, images: list[tuple[bytes, str]]) -> None:
    """Runs in a FastAPI BackgroundTask (its own thread, own DB session — the request's
    session is long gone by the time this executes) after start_verification's response has
    already been sent, so the professor is never blocked waiting on the AI call."""
    db = SessionLocal()
    try:
        verification = db.get(ClassroomVerification, verification_id)
        if verification is None:
            return
        try:
            _run_verification(db, verification, images)
        except Exception:  # noqa: BLE001 - a provider/parsing failure must not crash the worker
            logger.exception("Classroom verification failed verification_id=%s", verification_id)
            db.rollback()
            verification = db.get(ClassroomVerification, verification_id)
            if verification is not None:
                verification.status = VerificationStatus.FAILED
                verification.error_message = "Analysis failed. Please try again."
                verification.completed_at = utcnow()
                db.commit()
    finally:
        db.close()


def _run_verification(db: Session, verification: ClassroomVerification, images: list[tuple[bytes, str]]) -> None:
    lecture = db.get(Lecture, verification.lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)

    student_ids = [
        row[0] for row in db.query(Enrollment.student_id).filter(Enrollment.class_division_id == class_division.id).all()
    ]
    photos_by_student = (
        {
            p.student_id: p
            for p in db.query(StudentReferencePhoto).filter(StudentReferencePhoto.student_id.in_(student_ids)).all()
        }
        if student_ids
        else {}
    )
    students_by_id = (
        {s.id: s for s in db.query(StudentProfile).filter(StudentProfile.id.in_(photos_by_student.keys())).all()}
        if photos_by_student
        else {}
    )
    users_by_id = (
        {u.id: u for u in db.query(User).filter(User.id.in_([s.user_id for s in students_by_id.values()])).all()}
        if students_by_id
        else {}
    )

    references = [
        StudentReference(
            student_id=sid,
            full_name=users_by_id[students_by_id[sid].user_id].full_name,
            roll_number=students_by_id[sid].roll_number,
            image_bytes=photos_by_student[sid].image_data,
            content_type=photos_by_student[sid].content_type,
        )
        for sid in students_by_id
    ]

    present_student_ids = {
        row[0]
        for row in db.query(AttendanceRecord.student_id)
        .filter(AttendanceRecord.lecture_id == verification.lecture_id, AttendanceRecord.status.in_(PRESENT_LIKE))
        .all()
    }

    observations_by_student = {}
    if references:
        analysis = _get_provider().analyze_classroom([data for data, _ in images], references)
        observations_by_student = {o.student_id: o for o in analysis.observations}

    for sid in students_by_id:
        qr_present = sid in present_student_ids
        obs = observations_by_student.get(sid)
        confidence = obs.confidence if obs else 0.0
        ai_status = _bucket_confidence(confidence) if obs else DetectionStatus.NOT_DETECTED
        db.add(
            ClassroomVerificationResult(
                verification_id=verification.id,
                student_id=sid,
                qr_present=qr_present,
                ai_status=ai_status,
                confidence=confidence,
                discrepancy_type=_classify(qr_present, ai_status),
            )
        )

    verification.status = VerificationStatus.COMPLETED
    verification.completed_at = utcnow()
    db.commit()


def build_detail(db: Session, verification: ClassroomVerification) -> ClassroomVerificationDetailOut:
    lecture = db.get(Lecture, verification.lecture_id)
    enrolled_student_ids = [
        row[0]
        for row in db.query(Enrollment.student_id).filter(Enrollment.class_division_id == lecture.class_division_id).all()
    ]
    total_enrolled = len(enrolled_student_ids)
    # Computed directly (not as total_enrolled - len(results)) so it stays correct even when the
    # verification FAILED before producing any results — otherwise every enrolled student would
    # misleadingly show as "no reference photo" when the real cause was a provider failure.
    with_photo_count = (
        db.query(StudentReferencePhoto.id).filter(StudentReferencePhoto.student_id.in_(enrolled_student_ids)).count()
        if enrolled_student_ids
        else 0
    )
    students_excluded_no_reference_photo = max(total_enrolled - with_photo_count, 0)

    results = (
        db.query(ClassroomVerificationResult)
        .filter(ClassroomVerificationResult.verification_id == verification.id)
        .all()
    )
    student_ids = [r.student_id for r in results]
    students_by_id = (
        {s.id: s for s in db.query(StudentProfile).filter(StudentProfile.id.in_(student_ids)).all()} if student_ids else {}
    )
    users_by_id = (
        {u.id: u for u in db.query(User).filter(User.id.in_([s.user_id for s in students_by_id.values()])).all()}
        if students_by_id
        else {}
    )
    decisions_by_result = (
        {
            d.result_id: d
            for d in db.query(VerificationDecision).filter(VerificationDecision.result_id.in_([r.id for r in results])).all()
        }
        if results
        else {}
    )

    result_items: list[VerificationResultOut] = []
    present_count = confirmed_count = discrepancy_count = 0
    for r in results:
        student = students_by_id.get(r.student_id)
        user = users_by_id.get(student.user_id) if student else None
        decision = decisions_by_result.get(r.id)
        if r.qr_present:
            present_count += 1
        if r.discrepancy_type == DiscrepancyType.ATTENDED_AND_DETECTED:
            confirmed_count += 1
        elif r.discrepancy_type != DiscrepancyType.NONE:
            discrepancy_count += 1
        result_items.append(
            VerificationResultOut(
                id=r.id,
                student_id=r.student_id,
                full_name=user.full_name if user else "Unknown",
                roll_number=student.roll_number if student else "",
                qr_present=r.qr_present,
                ai_status=r.ai_status,
                confidence=float(r.confidence),
                discrepancy_type=r.discrepancy_type,
                decision_action=decision.action.value if decision else None,
                decision_notes=decision.notes if decision else None,
                decided_at=decision.created_at if decision else None,
            )
        )

    return ClassroomVerificationDetailOut(
        verification=ClassroomVerificationOut.model_validate(verification),
        total_enrolled=total_enrolled,
        students_excluded_no_reference_photo=students_excluded_no_reference_photo,
        present_count=present_count,
        confirmed_count=confirmed_count,
        discrepancy_count=discrepancy_count,
        results=result_items,
    )


def record_decision(
    db: Session,
    professor_profile: ProfessorProfile,
    result: ClassroomVerificationResult,
    payload: VerificationDecisionRequest,
) -> VerificationDecisionOut:
    existing = db.query(VerificationDecision).filter(VerificationDecision.result_id == result.id).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This discrepancy has already been reviewed")

    action = VerificationDecisionAction(payload.action)
    allowed = ALLOWED_ACTIONS.get(result.discrepancy_type)
    if not allowed or action not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{action.value}' is not a valid action for this discrepancy"
        )

    violation = None
    if action == VerificationDecisionAction.VIOLATION:
        verification = db.get(ClassroomVerification, result.verification_id)
        violation = violation_service.create_violation(
            db,
            professor_profile=professor_profile,
            student_id=result.student_id,
            lecture_id=verification.lecture_id,
            session_id=verification.session_id,
            verification_result_id=result.id,
            reason=payload.reason,
            notes=payload.notes,
            duration=payload.restriction_duration,
            custom_end=payload.custom_restriction_end,
        )

    decision = VerificationDecision(
        result_id=result.id, professor_id=professor_profile.id, action=action, notes=payload.notes
    )
    db.add(decision)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two requests raced past the "already reviewed" check above (uq_verification_decisions_result_id
        # is the actual guarantee). The loser's violation insert (if any) rolls back with it —
        # nothing half-applied.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This discrepancy has already been reviewed") from exc
    db.refresh(decision)

    return VerificationDecisionOut(
        result_id=result.id,
        action=decision.action.value,
        notes=decision.notes,
        created_at=decision.created_at,
        violation_id=violation.id if violation else None,
        restriction_end=violation.restriction_end if violation else None,
    )
