from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.rate_limit import limiter
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.services.auth_service import login_user, logout_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MeResponse, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    user = register_user(db, payload)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    token, user = login_user(db, payload, ip, user_agent)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


@router.post("/logout", status_code=204)
def logout(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    logout_user(db, current.user, current.session_id)
    return None


@router.get("/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user)):
    return current.user
