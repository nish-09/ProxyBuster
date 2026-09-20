import hmac
import logging
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import login_throttle
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.time import ensure_utc, utcnow
from app.models.security import Cooldown, DeviceSession, DeviceSessionStatus, SecurityEvent, SecurityEventSeverity
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.cooldown_service import get_active_cooldown

settings = get_settings()
logger = logging.getLogger("proxybusters.auth")

# Verified against when the email is unknown so a login for a non-existent account costs the same
# bcrypt time as one for a real account (no user-enumeration timing side channel).
_DUMMY_HASH = hash_password("proxybusters-timing-equaliser")


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def register_user(db: Session, payload: RegisterRequest) -> User:
    # Public self-registration is for students and (invite-gated) professors ONLY. Admin
    # accounts are provisioned out-of-band (backend/scripts/create_admin.py) — accepting
    # role=admin here would let anyone on the internet mint an administrator.
    if payload.role not in (UserRole.STUDENT, UserRole.PROFESSOR):
        logger.warning("Rejected public registration for privileged role %s", payload.role.value)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account type cannot be created via public registration")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    if payload.role == UserRole.PROFESSOR:
        # Public self-registration as a professor requires a backend-only invite code
        # (PROFESSOR_INVITE_CODE). An empty configured code means professor registration
        # is disabled entirely, not "any code accepted". Comparison is constant-time to
        # avoid leaking the code length/prefix via response timing. Never log the code or
        # the submitted value — only the pass/fail outcome matters.
        configured = settings.professor_invite_code
        submitted = payload.invite_code or ""
        if not configured or not hmac.compare_digest(submitted.encode(), configured.encode()):
            logger.warning("Professor registration rejected: invalid or missing invite code")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing professor invite code")
        if not payload.department:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "department is required for professors")
    else:
        if not settings.allow_public_student_registration:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Student accounts are created by your college administrator"
            )
        if not payload.roll_number or not payload.program or not payload.semester:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "roll_number, program, semester are required for students")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == UserRole.STUDENT:
        db.add(
            StudentProfile(
                user_id=user.id,
                roll_number=payload.roll_number,
                program=payload.program,
                semester=payload.semester,
            )
        )
    else:
        db.add(ProfessorProfile(user_id=user.id, department=payload.department))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Lost a race on the unique email / roll_number constraints.
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or roll number already registered") from exc
    db.refresh(user)
    logger.info("Registered %s account user_id=%s", user.role.value, user.id)
    return user


def login_user(db: Session, payload: LoginRequest, ip_address: str | None, user_agent: str | None) -> tuple[str, User]:
    wait = login_throttle.seconds_until_allowed(payload.email)
    if wait:
        logger.warning("Login blocked by brute-force protection for %s", _mask_email(payload.email))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            {"message": "Too many failed sign-in attempts. Please try again later.", "remaining_seconds": wait},
        )

    user = db.query(User).filter(User.email == payload.email).first()
    password_ok = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        login_throttle.record_failure(payload.email)
        logger.warning("Failed login for %s from %s", _mask_email(payload.email), ip_address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        logger.warning("Login refused for suspended account user_id=%s", user.id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is suspended")
    login_throttle.record_success(payload.email)

    if user.role == UserRole.STUDENT:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
        cooldown = get_active_cooldown(db, profile.id)
        # Only the voluntary-logout penalty blocks login. A short post-scan cooldown
        # (reason="attendance_marked", see attendance_service.scan) is meant to throttle
        # re-scanning, not to lock a student out of their own account/token refresh.
        if cooldown and cooldown.reason == "manual_logout":
            remaining = int((ensure_utc(cooldown.expires_at) - utcnow()).total_seconds())
            raise HTTPException(
                status.HTTP_423_LOCKED,
                {"message": "Account is in cooldown after logout", "remaining_seconds": max(remaining, 0)},
            )

    # Enforce one active session per account: invalidate any prior active sessions.
    prior_active = db.query(DeviceSession).filter(
        DeviceSession.user_id == user.id, DeviceSession.status == DeviceSessionStatus.ACTIVE
    ).all()
    if prior_active:
        for s in prior_active:
            s.status = DeviceSessionStatus.REVOKED
            s.logout_at = utcnow()
        db.add(
            SecurityEvent(
                user_id=user.id,
                event_type="concurrent_login",
                description="New login detected while a previous session was still active; prior session(s) revoked.",
                severity=SecurityEventSeverity.MEDIUM,
                event_metadata={"revoked_session_ids": [s.session_id for s in prior_active], "new_ip": ip_address},
            )
        )

    token, jti, expires_at = create_access_token(user_id=str(user.id), role=user.role.value)
    db.add(
        DeviceSession(
            user_id=user.id,
            session_id=jti,
            device_id=payload.device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status=DeviceSessionStatus.ACTIVE,
        )
    )
    db.commit()
    logger.info("Login ok user_id=%s role=%s", user.id, user.role.value)
    return token, user


def logout_user(db: Session, user: User, session_id: str) -> None:
    device_session = db.query(DeviceSession).filter(DeviceSession.session_id == session_id).first()
    if device_session and device_session.status == DeviceSessionStatus.ACTIVE:
        device_session.status = DeviceSessionStatus.LOGGED_OUT
        device_session.logout_at = utcnow()

    if user.role == UserRole.STUDENT:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
        db.add(
            Cooldown(
                student_id=profile.id,
                expires_at=utcnow() + timedelta(minutes=settings.cooldown_minutes),
                reason="manual_logout",
            )
        )
    db.commit()
