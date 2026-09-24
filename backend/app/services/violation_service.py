import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import ensure_utc, utcnow
from app.models.academic import Enrollment
from app.models.user import ProfessorProfile, StudentProfile, User
from app.models.verification import AttendanceViolation, ViolationReason, ViolationStatus
from app.schemas.verification import ViolationOut

settings = get_settings()

# Fixed-duration presets (see settings.restriction_one_lecture_hours / restriction_default_days
# for the configurable ones). "custom" is handled separately in compute_restriction_end.
_FIXED_DURATIONS = {
    "one_lecture": lambda: timedelta(hours=settings.restriction_one_lecture_hours),
    "one_day": lambda: timedelta(days=1),
    "three_days": lambda: timedelta(days=3),
    "seven_days": lambda: timedelta(days=settings.restriction_default_days),
}


def compute_restriction_end(now, duration: str, custom_end=None):
    if duration == "custom":
        if custom_end is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "custom_restriction_end is required for a custom duration"
            )
        custom_end = ensure_utc(custom_end)
        if custom_end <= now:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "custom_restriction_end must be in the future")
        return custom_end
    factory = _FIXED_DURATIONS.get(duration)
    if factory is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown restriction duration")
    return now + factory()


def create_violation(
    db: Session,
    *,
    professor_profile: ProfessorProfile,
    student_id: uuid.UUID,
    lecture_id: uuid.UUID,
    session_id: uuid.UUID | None,
    verification_result_id: uuid.UUID | None,
    reason: str,
    notes: str | None,
    duration: str,
    custom_end,
) -> AttendanceViolation:
    """Creates the violation row (flush only, no commit) — the caller commits alongside
    whatever else belongs in the same transaction (see
    app/services/verification/service.py::record_decision)."""
    now = utcnow()
    restriction_end = compute_restriction_end(now, duration, custom_end)
    violation = AttendanceViolation(
        student_id=student_id,
        lecture_id=lecture_id,
        session_id=session_id,
        professor_id=professor_profile.id,
        verification_result_id=verification_result_id,
        reason=ViolationReason(reason),
        notes=notes,
        status=ViolationStatus.ACTIVE,
        restriction_start=now,
        restriction_end=restriction_end,
    )
    db.add(violation)
    db.flush()
    return violation


def get_active_restriction(db: Session, student_id: uuid.UUID) -> AttendanceViolation | None:
    # Compare in Python (not SQL), same reasoning as cooldown_service.get_active_cooldown: works
    # identically whether the DB round-trips timezone-aware datetimes (Postgres) or strips
    # tzinfo (SQLite, used in tests).
    now = utcnow()
    candidates = (
        db.query(AttendanceViolation)
        .filter(AttendanceViolation.student_id == student_id, AttendanceViolation.status == ViolationStatus.ACTIVE)
        .order_by(AttendanceViolation.restriction_end.desc())
        .limit(5)
        .all()
    )
    for v in candidates:
        if ensure_utc(v.restriction_end) > now:
            return v
    return None


def _violation_out(db: Session, violation: AttendanceViolation) -> ViolationOut:
    student = db.get(StudentProfile, violation.student_id)
    user = db.get(User, student.user_id) if student else None
    return ViolationOut(
        id=violation.id,
        student_id=violation.student_id,
        full_name=user.full_name if user else "Unknown",
        roll_number=student.roll_number if student else "",
        lecture_id=violation.lecture_id,
        professor_id=violation.professor_id,
        reason=violation.reason.value,
        notes=violation.notes,
        status=violation.status,
        created_at=violation.created_at,
        restriction_start=violation.restriction_start,
        restriction_end=violation.restriction_end,
        revoked_at=violation.revoked_at,
        revocation_reason=violation.revocation_reason,
    )


def list_for_professor(
    db: Session, professor_profile: ProfessorProfile, class_division_id: uuid.UUID | None = None
) -> list[ViolationOut]:
    query = db.query(AttendanceViolation).filter(AttendanceViolation.professor_id == professor_profile.id)
    if class_division_id is not None:
        student_ids = [
            row[0]
            for row in db.query(Enrollment.student_id).filter(Enrollment.class_division_id == class_division_id).all()
        ]
        query = query.filter(AttendanceViolation.student_id.in_(student_ids))
    violations = query.order_by(AttendanceViolation.created_at.desc()).limit(200).all()
    return [_violation_out(db, v) for v in violations]


def list_all(db: Session) -> list[ViolationOut]:
    violations = db.query(AttendanceViolation).order_by(AttendanceViolation.created_at.desc()).limit(200).all()
    return [_violation_out(db, v) for v in violations]


def revoke(db: Session, violation: AttendanceViolation, revoked_by_user_id: uuid.UUID, revocation_reason: str) -> ViolationOut:
    if violation.status == ViolationStatus.REVOKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Violation already revoked")
    violation.status = ViolationStatus.REVOKED
    violation.revoked_at = utcnow()
    violation.revoked_by_user_id = revoked_by_user_id
    violation.revocation_reason = revocation_reason
    db.commit()
    db.refresh(violation)
    return _violation_out(db, violation)
