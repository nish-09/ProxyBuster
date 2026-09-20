import base64
import dataclasses
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import ensure_utc, utcnow
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.attendance import (
    AttendanceMethod,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    AttendanceToken,
    ManualAttendance,
    SessionStatus,
)
from app.models.security import Cooldown
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole
from app.schemas.attendance import ManualAttendanceRequest
from app.services.cooldown_service import get_active_cooldown

settings = get_settings()
logger = logging.getLogger("proxybusters.attendance")

SCAN_COOLDOWN_REASON = "attendance_marked"

# A scheduled lecture can be started this long before its scheduled_start (professors walk in
# early), but not days ahead.
EARLY_START_GRACE = timedelta(minutes=30)
PRESENT_LIKE = (AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.MANUAL)


def api_error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    """Structured error body: {"detail": {"code": ..., "message": ..., **extra}}.

    `code` is a stable machine-readable identifier the frontend switches on (instead of
    pattern-matching English messages); `message` is safe to show to the user.
    """
    return HTTPException(status_code, {"code": code, "message": message, **extra})


@dataclasses.dataclass
class ScanOutcome:
    attendance_status: str
    marked_at: datetime
    class_division_id: uuid.UUID
    subject_code: str
    subject_name: str
    division_name: str
    lecture_topic: str | None
    cooldown_seconds: int
    cooldown_expires_at: datetime
    session_id: uuid.UUID
    student_name: str
    roll_number: str
    present_count: int
    total_enrolled: int


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


def authorize_session_owner(db: Session, session_id: uuid.UUID, user: User) -> AttendanceSession:
    """Only the professor who owns the session. Used for the live WebSocket: the feed carries the
    rotating QR and every student's check-in, so an enrolled student must NOT be able to
    subscribe (they could read the QR remotely and scan it from outside the room)."""
    if user.role != UserRole.PROFESSOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the session's professor can subscribe")
    return authorize_session_access(db, session_id, user)


def _assert_can_start(db: Session, class_division: ClassDivision, lecture: Lecture) -> None:
    """Validation shared by scheduled and ad-hoc starts. Takes a row lock on the class
    division so two concurrent starts for the same class serialise instead of racing."""
    now = utcnow()
    if now > ensure_utc(lecture.scheduled_end):
        raise HTTPException(status.HTTP_409_CONFLICT, "This lecture has already ended")
    if now < ensure_utc(lecture.scheduled_start) - EARLY_START_GRACE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This lecture has not started yet")

    db.query(ClassDivision).filter(ClassDivision.id == class_division.id).with_for_update().first()

    if db.query(Enrollment).filter(Enrollment.class_division_id == class_division.id).first() is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No students are enrolled in this division yet")

    expire_overdue_sessions(db)
    active_for_division = (
        db.query(AttendanceSession.id)
        .join(Lecture, Lecture.id == AttendanceSession.lecture_id)
        .filter(Lecture.class_division_id == class_division.id, AttendanceSession.status == SessionStatus.ACTIVE)
        .first()
    )
    if active_for_division is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An attendance session is already active for this class")


def _start_session(db: Session, professor_profile: ProfessorProfile, lecture: Lecture) -> AttendanceSession:
    session_obj = AttendanceSession(
        id=uuid.uuid4(),  # set explicitly (not left to the column default) so _build_token
        # below can use session_obj.id before this row is flushed — SQLAlchemy only applies
        # `default=` callables at flush time, not at construction time.
        lecture_id=lecture.id,
        professor_id=professor_profile.id,
        status=SessionStatus.ACTIVE,
    )
    db.add(session_obj)
    # The first token is built (client-side id, see _build_token) and inserted in the SAME
    # transaction as the session row — one commit/round-trip instead of two — so the "first
    # QR" is available to the caller one full DB round-trip sooner.
    db.add(_build_token(session_obj))
    try:
        db.commit()
    except IntegrityError as exc:
        # The read-then-write checks are a fast path / friendly message. The actual guarantee
        # is the partial unique index on (lecture_id) WHERE status = 'ACTIVE' (migration
        # 9ebaabdae366): if two requests race past the checks, only one INSERT wins and the loser
        # lands here — its token insert rolls back with it, so no orphaned token is left behind.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An attendance session is already active for this lecture") from exc
    db.refresh(session_obj)
    logger.info("Session started session_id=%s lecture_id=%s professor_id=%s", session_obj.id, lecture.id, professor_profile.id)
    return session_obj


def create_session(db: Session, professor_profile: ProfessorProfile, lecture_id: uuid.UUID) -> AttendanceSession:
    lecture = _lecture_or_404(db, lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)
    if class_division is None or class_division.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")
    _assert_can_start(db, class_division, lecture)
    return _start_session(db, professor_profile, lecture)


def create_adhoc_session(
    db: Session,
    professor_profile: ProfessorProfile,
    class_division_id: uuid.UUID,
    duration_minutes: int,
    topic: str | None,
) -> AttendanceSession:
    """Starts attendance for a class that has no pre-scheduled Lecture yet.

    Reuses the existing Lecture + AttendanceSession models: creates a Lecture starting now
    (scheduled_end = now + duration_minutes, which doubles as this session's expiry — see
    _expire_if_overdue) and starts a normal session for it, in ONE transaction: a failed or
    rejected start never leaves an orphan Lecture (an empty extra column on the sheet) behind.
    """
    class_division = db.get(ClassDivision, class_division_id)
    if class_division is None or class_division.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")

    now = utcnow()
    lecture = Lecture(
        id=uuid.uuid4(),
        class_division_id=class_division_id,
        topic=topic or "Ad-hoc Session",
        scheduled_start=now,
        scheduled_end=now + timedelta(minutes=duration_minutes),
        room=class_division.room,
    )
    _assert_can_start(db, class_division, lecture)
    db.add(lecture)
    db.flush()
    return _start_session(db, professor_profile, lecture)


def _mark_expired(db: Session, session_id: uuid.UUID, ended_at: datetime) -> None:
    """Conditional ACTIVE -> EXPIRED transition. Safe to race: only the caller whose UPDATE
    actually matches an ACTIVE row changes anything."""
    result = db.execute(
        update(AttendanceSession)
        .where(AttendanceSession.id == session_id, AttendanceSession.status == SessionStatus.ACTIVE)
        .values(status=SessionStatus.EXPIRED, ended_at=ended_at)
    )
    db.commit()
    if result.rowcount:
        logger.info("Session expired session_id=%s", session_id)


def _expire_if_overdue(db: Session, session_obj: AttendanceSession, lecture: Lecture) -> bool:
    """Lazily transitions an ACTIVE session to EXPIRED once its lecture's scheduled_end has
    passed (the sweeper and the QR rotation loop do the same proactively). Returns True if the
    session is (now) not ACTIVE."""
    if session_obj.status != SessionStatus.ACTIVE:
        return True
    if utcnow() <= ensure_utc(lecture.scheduled_end):
        return False
    _mark_expired(db, session_obj.id, ensure_utc(lecture.scheduled_end))
    db.refresh(session_obj)
    return True


def expire_overdue_sessions(db: Session) -> int:
    """Expire every ACTIVE session whose lecture has ended. Returns how many were expired."""
    overdue = (
        db.query(AttendanceSession.id, Lecture.scheduled_end)
        .join(Lecture, Lecture.id == AttendanceSession.lecture_id)
        .filter(AttendanceSession.status == SessionStatus.ACTIVE)
        .all()
    )
    now = utcnow()
    count = 0
    for session_id, scheduled_end in overdue:
        if now > ensure_utc(scheduled_end):
            _mark_expired(db, session_id, ensure_utc(scheduled_end))
            count += 1
    return count


def _build_token(session_obj: AttendanceSession) -> AttendanceToken:
    """Constructs a signed AttendanceToken without touching the DB. session_obj.id is safe to
    use here even before that row is committed — GUID primary keys are generated client-side
    (default=uuid.uuid4 on the model), not by the database — which is what lets _start_session
    fold the session insert and its first token into a single commit/round-trip."""
    nonce = secrets.token_urlsafe(16)
    issued_at = utcnow()
    expires_at = issued_at + timedelta(seconds=settings.qr_token_ttl_seconds)

    signing_payload = f"{session_obj.id}.{nonce}.{int(issued_at.timestamp())}.{int(expires_at.timestamp())}"
    signature = hmac.new(
        settings.qr_signing_secret.encode(), signing_payload.encode(), hashlib.sha256
    ).hexdigest()

    return AttendanceToken(
        session_id=session_obj.id,
        nonce=nonce,
        signature=signature,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def issue_token(db: Session, session_obj: AttendanceSession) -> AttendanceToken:
    token = _build_token(session_obj)
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
    # Only an unexpired AND unconsumed token is worth showing: a consumed one is dead — the next
    # scan against it would be rejected — so it must not be handed back to the professor's screen.
    token = (
        db.query(AttendanceToken)
        .filter(AttendanceToken.session_id == session_obj.id, AttendanceToken.consumed.is_(False))
        .order_by(AttendanceToken.issued_at.desc())
        .first()
    )
    if token is None or ensure_utc(token.expires_at) <= utcnow():
        return None
    return token


def get_or_issue_current_token(db: Session, session_obj: AttendanceSession) -> AttendanceToken | None:
    """Returns None (no more QR rotation) once the session is no longer ACTIVE — callers use
    this to stop showing a scannable QR for an expired or closed session."""
    lecture = db.get(Lecture, session_obj.lecture_id)
    if _expire_if_overdue(db, session_obj, lecture):
        return None
    token = _current_token(db, session_obj)
    if token is None:
        token = issue_token(db, session_obj)
    return token


def _parse_qr(raw_payload: str) -> tuple[str, str]:
    """Returns (session_id_str, nonce) after verifying the HMAC. Pure — no DB access — so a
    forged/tampered payload is rejected before it can cost a query."""
    try:
        decoded = base64.urlsafe_b64decode(raw_payload.encode()).decode()
        session_id_str, nonce, issued_at_ts, expires_at_ts, signature = decoded.split(".", 4)
        signing_payload = f"{session_id_str}.{nonce}.{issued_at_ts}.{expires_at_ts}"
        expected_signature = hmac.new(
            settings.qr_signing_secret.encode(), signing_payload.encode(), hashlib.sha256
        ).hexdigest()
    except Exception as exc:  # noqa: BLE001 - any parse failure is an invalid QR
        raise api_error(status.HTTP_400_BAD_REQUEST, "invalid_qr", "This is not a valid attendance QR code.") from exc

    if not hmac.compare_digest(expected_signature, signature):
        raise api_error(status.HTTP_400_BAD_REQUEST, "invalid_qr", "This is not a valid attendance QR code.")
    return session_id_str, nonce


def counts_for_ids(db: Session, lecture_id: uuid.UUID, class_division_id: uuid.UUID) -> tuple[int, int]:
    """(present_count, total_enrolled) — both counts in ONE round trip."""
    total_enrolled = (
        select(func.count()).select_from(Enrollment).where(Enrollment.class_division_id == class_division_id).scalar_subquery()
    )
    present_count = (
        select(func.count())
        .select_from(AttendanceRecord)
        .where(AttendanceRecord.lecture_id == lecture_id, AttendanceRecord.status.in_(PRESENT_LIKE))
        .scalar_subquery()
    )
    present, total = db.execute(select(present_count, total_enrolled)).one()
    return int(present), int(total)


def counts_for_lecture(db: Session, lecture: Lecture) -> tuple[int, int]:
    """(present_count, total_enrolled) for a lecture — straight from the database."""
    return counts_for_ids(db, lecture.id, lecture.class_division_id)


def scan(
    db: Session, student_profile: StudentProfile, raw_payload: str, ip_address: str | None
) -> ScanOutcome:
    session_id_str, nonce = _parse_qr(raw_payload)

    token = db.query(AttendanceToken).filter(AttendanceToken.nonce == nonce).first()
    if token is None or str(token.session_id) != session_id_str:
        raise api_error(status.HTTP_400_BAD_REQUEST, "invalid_qr", "This is not a valid attendance QR code.")

    # Shared row lock on the session for the rest of this transaction: concurrent scans
    # proceed in parallel, but close_session (FOR UPDATE) waits for in-flight scans and any
    # scan that starts after the close sees CLOSED — no attendance slips in after a stop.
    session_obj = (
        db.query(AttendanceSession).filter(AttendanceSession.id == token.session_id).with_for_update(read=True).first()
    )
    if session_obj is None:
        raise api_error(status.HTTP_409_CONFLICT, "session_closed", "Attendance session has ended.")

    if token.consumed:
        logger.info("Scan rejected: QR already used session_id=%s", session_obj.id)
        raise api_error(status.HTTP_409_CONFLICT, "qr_used", "That QR code was just used. Scan the new one on screen.")
    if ensure_utc(token.expires_at) <= utcnow():
        raise api_error(status.HTTP_410_GONE, "qr_expired", "QR code expired, please rescan.")

    lecture = db.get(Lecture, session_obj.lecture_id)
    if session_obj.status == SessionStatus.ACTIVE and utcnow() > ensure_utc(lecture.scheduled_end):
        db.rollback()  # drop the shared lock before the conditional UPDATE below
        _mark_expired(db, session_obj.id, ensure_utc(lecture.scheduled_end))
        raise api_error(status.HTTP_410_GONE, "session_expired", "Attendance session has expired.")
    if session_obj.status == SessionStatus.EXPIRED:
        raise api_error(status.HTTP_410_GONE, "session_expired", "Attendance session has expired.")
    if session_obj.status != SessionStatus.ACTIVE:
        raise api_error(status.HTTP_409_CONFLICT, "session_closed", "Attendance session has ended.")

    class_division, subject = (
        db.query(ClassDivision, Subject)
        .join(Subject, Subject.id == ClassDivision.subject_id)
        .filter(ClassDivision.id == lecture.class_division_id)
        .one()
    )

    # Serialise this student's own scans (two tabs, double taps, two devices): the checks below
    # and the insert are then one atomic step per student, so the cooldown can't be raced past.
    # (Also fetches the display name for the professor's live feed in the same round trip.)
    _profile, student_name = (
        db.query(StudentProfile, User.full_name)
        .join(User, User.id == StudentProfile.user_id)
        .filter(StudentProfile.id == student_profile.id)
        .with_for_update(of=StudentProfile)
        .one()
    )

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student_profile.id, Enrollment.class_division_id == class_division.id)
        .first()
    )
    if enrollment is None:
        raise api_error(status.HTTP_403_FORBIDDEN, "not_enrolled", "You are not enrolled in this class.")

    # Checked before the cooldown so re-scanning the *same* lecture's QR (a double tap, a second
    # tab) reports the more specific "already marked" instead of a generic cooldown message.
    existing_record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_profile.id, AttendanceRecord.lecture_id == lecture.id)
        .first()
    )
    if existing_record:
        raise api_error(status.HTTP_409_CONFLICT, "already_marked", "Attendance already marked for this lecture.")

    cooldown = get_active_cooldown(db, student_profile.id)
    if cooldown:
        remaining = int((ensure_utc(cooldown.expires_at) - utcnow()).total_seconds())
        raise api_error(
            status.HTTP_423_LOCKED,
            "cooldown",
            "Attendance already marked. Please wait before scanning again.",
            remaining_seconds=max(remaining, 0),
        )

    marked_at = utcnow()
    attendance_status = AttendanceStatus.PRESENT
    if marked_at - ensure_utc(lecture.scheduled_start) > timedelta(minutes=15):
        attendance_status = AttendanceStatus.LATE

    # Atomic single-use consumption: the UPDATE only matches while the token is still
    # unconsumed, so of two concurrent scans of the same QR exactly one gets rowcount == 1.
    # It shares a transaction with the record insert below — if that insert fails the token
    # is NOT burned, so a disallowed scan can't burn the QR for the real student.
    consumed = db.execute(
        update(AttendanceToken)
        .where(AttendanceToken.id == token.id, AttendanceToken.consumed.is_(False))
        .values(consumed=True, consumed_by=student_profile.id, consumed_at=marked_at)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise api_error(status.HTTP_409_CONFLICT, "qr_used", "That QR code was just used. Scan the new one on screen.")

    # Everything the response needs, captured BEFORE the commit: commit expires ORM instances and
    # reading them afterwards would cost one extra SELECT per attribute.
    session_id = session_obj.id
    lecture_id = lecture.id
    class_division_id = class_division.id
    roll_number = student_profile.roll_number
    subject_code, subject_name = subject.code, subject.name
    division_name, lecture_topic = class_division.name, lecture.topic

    record = AttendanceRecord(
        student_id=student_profile.id,
        lecture_id=lecture_id,
        session_id=session_id,
        status=attendance_status,
        method=AttendanceMethod.QR,
        marked_at=marked_at,
    )
    # Server-enforced post-scan cooldown (see settings.scan_cooldown_seconds): written in the
    # SAME transaction as the attendance record, so a client never observes a 200 response for
    # which the cooldown wasn't actually persisted alongside it.
    cooldown_seconds = settings.scan_cooldown_seconds
    cooldown_expires_at = marked_at + timedelta(seconds=cooldown_seconds)
    new_cooldown = Cooldown(
        student_id=student_profile.id, expires_at=cooldown_expires_at, reason=SCAN_COOLDOWN_REASON
    )

    try:
        db.add(record)
        db.add(new_cooldown)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise api_error(status.HTTP_409_CONFLICT, "already_marked", "Attendance already marked for this lecture.") from exc

    present_count, total_enrolled = counts_for_ids(db, lecture_id, class_division_id)
    logger.info("Attendance marked session_id=%s status=%s", session_id, attendance_status.value)
    return ScanOutcome(
        attendance_status=attendance_status.value,
        marked_at=marked_at,
        class_division_id=class_division_id,
        subject_code=subject_code,
        subject_name=subject_name,
        division_name=division_name,
        lecture_topic=lecture_topic,
        cooldown_seconds=cooldown_seconds,
        cooldown_expires_at=cooldown_expires_at,
        session_id=session_id,
        student_name=student_name,
        roll_number=roll_number,
        present_count=present_count,
        total_enrolled=total_enrolled,
    )


def close_session(db: Session, professor_profile: ProfessorProfile, session_id: uuid.UUID) -> AttendanceSession:
    # FOR UPDATE: waits for scans already in flight (they hold a shared lock) and blocks new
    # ones until this commits, so the CLOSED transition is a clean cut-off point.
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).with_for_update().first()
    if session_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session_obj.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")
    if session_obj.status != SessionStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session has already ended")

    lecture = db.get(Lecture, session_obj.lecture_id)
    if utcnow() > ensure_utc(lecture.scheduled_end):
        session_obj.status = SessionStatus.EXPIRED
        session_obj.ended_at = ensure_utc(lecture.scheduled_end)
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Session has already ended")

    # "Absent" is not stored: it is defined as enrolled-minus-recorded for a lecture,
    # computed at read time by analytics_service. Closing the session only stops the
    # QR rotation and freezes further scans against it.
    session_obj.status = SessionStatus.CLOSED
    session_obj.ended_at = utcnow()
    db.commit()
    db.refresh(session_obj)
    logger.info("Session closed session_id=%s by professor_id=%s", session_obj.id, professor_profile.id)
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

    try:
        db.flush()
    except IntegrityError as exc:
        # A student's own QR scan landed between our lookup and insert.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Attendance changed concurrently - please retry") from exc

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
