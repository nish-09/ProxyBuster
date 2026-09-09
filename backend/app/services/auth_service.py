from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.time import ensure_utc, utcnow
from app.models.security import Cooldown, DeviceSession, DeviceSessionStatus, SecurityEvent, SecurityEventSeverity
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.cooldown_service import get_active_cooldown

settings = get_settings()


def register_user(db: Session, payload: RegisterRequest) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == UserRole.STUDENT:
        if not payload.roll_number or not payload.program or not payload.semester:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "roll_number, program, semester are required for students")
        db.add(
            StudentProfile(
                user_id=user.id,
                roll_number=payload.roll_number,
                program=payload.program,
                semester=payload.semester,
            )
        )
    else:
        if not payload.department:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "department is required for professors")
        db.add(ProfessorProfile(user_id=user.id, department=payload.department))

    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, payload: LoginRequest, ip_address: str | None, user_agent: str | None) -> tuple[str, User]:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is suspended")

    if user.role == UserRole.STUDENT:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
        cooldown = get_active_cooldown(db, profile.id)
        if cooldown:
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
