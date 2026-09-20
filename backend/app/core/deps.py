import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.security import DeviceSession, DeviceSessionStatus
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user: User, session_id: str):
        self.user = user
        self.session_id = session_id


def authenticate(token: str, db: Session) -> CurrentUser:
    """Shared token->CurrentUser resolution, used by both the HTTP bearer dependency and
    the WebSocket handshake (which cannot send an Authorization header)."""
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    jti = payload.get("jti")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    device_session = (
        db.query(DeviceSession)
        .filter(DeviceSession.session_id == jti, DeviceSession.status == DeviceSessionStatus.ACTIVE)
        .first()
    )
    if device_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been invalidated. Please log in again.")

    return CurrentUser(user=user, session_id=jti)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return authenticate(credentials.credentials, db)


def require_role(*roles: UserRole):
    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return current

    return dependency


require_student = require_role(UserRole.STUDENT)
require_professor = require_role(UserRole.PROFESSOR)
require_admin = require_role(UserRole.ADMIN)


def get_student_profile(current: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current.user.id).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student profile not found")
    return profile


def get_professor_profile(
    current: CurrentUser = Depends(require_professor), db: Session = Depends(get_db)
) -> ProfessorProfile:
    profile = db.query(ProfessorProfile).filter(ProfessorProfile.user_id == current.user.id).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Professor profile not found")
    return profile
