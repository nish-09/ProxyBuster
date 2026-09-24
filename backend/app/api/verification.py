import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_professor_profile
from app.core.rate_limit import limiter, user_or_ip_key
from app.models.attendance import AttendanceSession
from app.models.user import ProfessorProfile
from app.models.verification import AttendanceViolation, ClassroomVerification, ClassroomVerificationResult
from app.schemas.verification import (
    ClassroomVerificationDetailOut,
    ClassroomVerificationOut,
    RevokeViolationRequest,
    VerificationDecisionOut,
    VerificationDecisionRequest,
    ViolationOut,
)
from app.services import violation_service
from app.services.verification import service as verification_service

router = APIRouter(prefix="/verification", tags=["verification"])
settings = get_settings()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _read_and_validate_images(files: list[UploadFile]) -> list[tuple[bytes, str]]:
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least 1 classroom photo is required")
    if len(files) > settings.classroom_verification_max_images:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Up to {settings.classroom_verification_max_images} photos are allowed per verification",
        )
    images: list[tuple[bytes, str]] = []
    for f in files:
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported image type: {f.content_type}")
        data = f.file.read()
        if not data:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One of the uploaded images is empty")
        if len(data) > settings.classroom_verification_max_image_bytes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One of the uploaded images is too large")
        images.append((data, f.content_type))
    return images


@router.post("/sessions/{session_id}/verify", response_model=ClassroomVerificationOut, status_code=202)
@limiter.limit("10/minute", key_func=user_or_ip_key)
def start_verification(
    request: Request,
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(...),
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    """Rate-limited (unlike most professor endpoints): each call makes a real, paid call to the
    configured AI provider — see app/services/verification/anthropic_provider.py — so this is
    also a cost-control measure, not just abuse prevention."""
    session_obj = db.get(AttendanceSession, session_id)
    if session_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session_obj.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")

    image_data = _read_and_validate_images(images)
    verification = verification_service.start_verification(db, professor_profile, session_obj, image_data)
    # Runs after this response is sent (Starlette threadpools a sync BackgroundTask), so the
    # professor's request returns immediately instead of waiting out the AI call — see
    # app/services/verification/service.py::run_verification_job.
    background_tasks.add_task(verification_service.run_verification_job, verification.id, image_data)
    return verification


def _verification_or_404_owned(
    db: Session, verification_id: uuid.UUID, professor_profile: ProfessorProfile
) -> ClassroomVerification:
    verification = db.get(ClassroomVerification, verification_id)
    if verification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    if verification.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this verification")
    return verification


@router.get("/{verification_id}", response_model=ClassroomVerificationDetailOut)
def get_verification(
    verification_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    verification = _verification_or_404_owned(db, verification_id, professor_profile)
    return verification_service.build_detail(db, verification)


@router.post("/results/{result_id}/decision", response_model=VerificationDecisionOut)
def decide_result(
    result_id: uuid.UUID,
    payload: VerificationDecisionRequest,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    result = db.get(ClassroomVerificationResult, result_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Result not found")
    verification = db.get(ClassroomVerification, result.verification_id)
    if verification is None or verification.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this verification")
    return verification_service.record_decision(db, professor_profile, result, payload)


@router.get("/violations/mine", response_model=list[ViolationOut])
def list_my_violations(
    class_division_id: uuid.UUID | None = None,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    return violation_service.list_for_professor(db, professor_profile, class_division_id)


@router.post("/violations/{violation_id}/revoke", response_model=ViolationOut)
def revoke_violation(
    violation_id: uuid.UUID,
    payload: RevokeViolationRequest,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    violation = db.get(AttendanceViolation, violation_id)
    if violation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Violation not found")
    if violation.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You did not create this violation")
    return violation_service.revoke(db, violation, professor_profile.user_id, payload.revocation_reason)
