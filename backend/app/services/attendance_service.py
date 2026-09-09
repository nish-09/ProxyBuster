import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import ensure_utc, utcnow
from app.models.academic import ClassDivision, Enrollment, Lecture
from app.models.attendance import (
    AttendanceMethod,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    AttendanceToken,
    ManualAttendance,
    SessionStatus,
)
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole
from app.schemas.attendance import ManualAttendanceRequest
from app.services.cooldown_service import get_active_cooldown

settings = get_settings()


def _lecture_or_404(db: Session, lecture_id: uuid.UUID) -> Lecture:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lecture not found")
    return lecture


def authorize_session_access(db: Session, session_id: uuid.UUID, user: User) -> AttendanceSession:
    """Verify `user` (professor who owns it, or a student enrolled in it) may view/subscribe to this session.

    Raises HTTPException(404/403) otherwise. Shared by the REST `GET /sessions/{id}` endpoint
    and the WebSocket handshake, so a student can't snoop another class's live feed.
    """
    session_obj = db.get(AttendanceSession, session_id)
    if session_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    lecture = db.get(Lecture, session_obj.lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)

    if user.role == UserRole.PROFESSOR:
        professor_profile = db.query(ProfessorProfile).filter(ProfessorProfile.user_id == user.id).first()
        if professor_profile is None or class_division.professor_id != professor_profile.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")
    else:
        student_profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
        enrolled = (
            student_profile
            and db.query(Enrollment)
            .filter(Enrollment.student_id == student_profile.id, Enrollment.class_division_id == class_division.id)
            .first()
        )
        if not enrolled:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not enrolled in this class")

    return session_obj


def create_session(db: Session, professor_profile: ProfessorProfile, lecture_id: uuid.UUID) -> AttendanceSession:
    lecture = _lecture_or_404(db, lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)
    if class_division is None or class_division.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")

    existing_active = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.lecture_id == lecture_id, AttendanceSession.status == SessionStatus.ACTIVE)
        .first()
    )
    if existing_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "An attendance session is already active for this lecture")

    session_obj = AttendanceSession(
        lecture_id=lecture_id,
        professor_id=professor_profile.id,
        status=SessionStatus.ACTIVE,
    )
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)

    issue_token(db, session_obj)
    return session_obj


def issue_token(db: Session, session_obj: AttendanceSession) -> AttendanceToken:
    nonce = secrets.token_urlsafe(16)
    issued_at = utcnow()
    expires_at = issued_at + timedelta(seconds=settings.qr_token_ttl_seconds)

    signing_payload = f"{session_obj.id}.{nonce}.{int(issued_at.timestamp())}.{int(expires_at.timestamp())}"
    signature = hmac.new(
        settings.qr_signing_secret.encode(), signing_payload.encode(), hashlib.sha256
    ).hexdigest()

    token = AttendanceToken(
        session_id=session_obj.id,
        nonce=nonce,
        signature=signature,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def encode_qr_payload(token: AttendanceToken) -> str:
    raw = (
        f"{token.session_id}.{token.nonce}.{int(ensure_utc(token.issued_at).timestamp())}."
        f"{int(ensure_utc(token.expires_at).timestamp())}.{token.signature}"
    )
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _current_token(db: Session, session_obj: AttendanceSession) -> AttendanceToken | None:
    token = (
        db.query(AttendanceToken)
        .filter(AttendanceToken.session_id == session_obj.id)
        .order_by(AttendanceToken.issued_at.desc())
        .first()
    )
    if token is None or ensure_utc(token.expires_at) < utcnow():
        return None
    return token


def get_or_issue_current_token(db: Session, session_obj: AttendanceSession) -> AttendanceToken:
    token = _current_token(db, session_obj)
    if token is None:
        token = issue_token(db, session_obj)
    return token


def decode_and_verify_scan(db: Session, raw_payload: str) -> AttendanceToken:
    try:
        decoded = base64.urlsafe_b64decode(raw_payload.encode()).decode()
        session_id_str, nonce, issued_at_ts, expires_at_ts, signature = decoded.split(".", 4)
        signing_payload = f"{session_id_str}.{nonce}.{issued_at_ts}.{expires_at_ts}"
        expected_signature = hmac.new(
            settings.qr_signing_secret.encode(), signing_payload.encode(), hashlib.sha256
        ).hexdigest()
    except Exception as exc:  # noqa: BLE001 - any parse failure is an invalid QR
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid QR code") from exc

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid QR code")

    token = db.query(AttendanceToken).filter(AttendanceToken.nonce == nonce).first()
    if token is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid QR code")

    if token.consumed:
        raise HTTPException(status.HTTP_409_CONFLICT, "QR code already used")

    if ensure_utc(token.expires_at) < utcnow():
        raise HTTPException(status.HTTP_410_GONE, "QR code expired, please rescan")

    session_obj = db.get(AttendanceSession, token.session_id)
    if session_obj is None or session_obj.status != SessionStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Attendance session is closed")

    return token


def scan(
    db: Session, student_profile: StudentProfile, raw_payload: str, ip_address: str | None
) -> tuple[AttendanceRecord, uuid.UUID]:
    token = decode_and_verify_scan(db, raw_payload)
    session_obj = db.get(AttendanceSession, token.session_id)
    lecture = db.get(Lecture, session_obj.lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student_profile.id, Enrollment.class_division_id == class_division.id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not enrolled in this class")

    cooldown = get_active_cooldown(db, student_profile.id)
    if cooldown:
        remaining = int((ensure_utc(cooldown.expires_at) - utcnow()).total_seconds())
        raise HTTPException(
            status.HTTP_423_LOCKED,
            {"message": "Your account is in cooldown", "remaining_seconds": max(remaining, 0)},
        )

    existing_record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_profile.id, AttendanceRecord.lecture_id == lecture.id)
        .first()
    )
    if existing_record:
        raise HTTPException(status.HTTP_409_CONFLICT, "Attendance already marked for this lecture")

    marked_at = utcnow()
    attendance_status = AttendanceStatus.PRESENT
    if marked_at - ensure_utc(lecture.scheduled_start) > timedelta(minutes=15):
        attendance_status = AttendanceStatus.LATE

    record = AttendanceRecord(
        student_id=student_profile.id,
        lecture_id=lecture.id,
        session_id=session_obj.id,
        status=attendance_status,
        method=AttendanceMethod.QR,
        marked_at=marked_at,
    )
    token.consumed = True
    token.consumed_by = student_profile.id
    token.consumed_at = marked_at

    try:
        db.add(record)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Attendance already marked for this lecture") from exc

    db.refresh(record)
    return record, class_division.id


def close_session(db: Session, professor_profile: ProfessorProfile, session_id: uuid.UUID) -> AttendanceSession:
    session_obj = db.get(AttendanceSession, session_id)
    if session_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session_obj.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")
    if session_obj.status != SessionStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is already closed")

    # "Absent" is not stored: it is defined as enrolled-minus-recorded for a lecture,
    # computed at read time by analytics_service. Closing the session only stops the
    # QR rotation and freezes further scans against it.
    session_obj.status = SessionStatus.CLOSED
    session_obj.ended_at = utcnow()
    db.commit()
    db.refresh(session_obj)
    return session_obj


def manual_mark(
    db: Session, professor_profile: ProfessorProfile, payload: ManualAttendanceRequest
) -> ManualAttendance:
    lecture = _lecture_or_404(db, payload.lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)
    if class_division is None or class_division.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == payload.student_id, Enrollment.class_division_id == class_division.id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Student is not enrolled in this class")

    new_status = AttendanceStatus(payload.status)

    record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == payload.student_id, AttendanceRecord.lecture_id == lecture.id)
        .first()
    )
    previous_status = record.status.value if record else None

    if record is None:
        record = AttendanceRecord(
            student_id=payload.student_id,
            lecture_id=lecture.id,
            session_id=None,
            status=new_status,
            method=AttendanceMethod.MANUAL,
            marked_at=utcnow(),
        )
        db.add(record)
    else:
        record.status = new_status
        record.method = AttendanceMethod.MANUAL
        record.marked_at = utcnow()

    db.flush()

    audit = ManualAttendance(
        attendance_record_id=record.id,
        professor_id=professor_profile.id,
        reason=payload.reason,
        previous_status=previous_status,
        new_status=new_status.value,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit
