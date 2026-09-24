import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.security import DeviceBinding, DeviceBindingStatus
from app.models.user import StudentProfile

logger = logging.getLogger("proxybusters.device_binding")


def check_and_bind(db: Session, student_profile: StudentProfile, device_id: str | None) -> None:
    """Called from auth_service.login_user for STUDENT logins only. A blank/missing device_id
    means the client can't identify itself, so there's nothing to bind or check — never block a
    login over an absent value. Raises 403 if this device_id is already bound to a DIFFERENT
    student; otherwise binds it (first time) or no-ops (already bound to this same student)."""
    if not device_id:
        return

    existing = db.query(DeviceBinding).filter(
        DeviceBinding.device_id == device_id, DeviceBinding.status == DeviceBindingStatus.ACTIVE
    ).first()
    if existing is not None:
        if existing.student_id != student_profile.id:
            logger.warning(
                "Login rejected: device_id already bound to a different student student_id=%s", existing.student_id
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {
                    "code": "device_registered_to_another_student",
                    "message": "This device is already registered to another student account. Contact your professor or admin if this is a mistake.",
                },
            )
        return  # already bound to this same student — fine

    db.add(DeviceBinding(device_id=device_id, student_id=student_profile.id))
    try:
        db.flush()
    except IntegrityError as exc:
        # Lost a race: another login just bound this device_id first (partial unique index on
        # (device_id) WHERE status = 'ACTIVE'). Re-check who won rather than assuming failure.
        db.rollback()
        winner = db.query(DeviceBinding).filter(
            DeviceBinding.device_id == device_id, DeviceBinding.status == DeviceBindingStatus.ACTIVE
        ).first()
        if winner is None or winner.student_id != student_profile.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {
                    "code": "device_registered_to_another_student",
                    "message": "This device is already registered to another student account. Contact your professor or admin if this is a mistake.",
                },
            ) from exc


def reset_for_student(db: Session, student_id: uuid.UUID, revoked_by_user_id: uuid.UUID, reason: str | None = None) -> int:
    """Frees every device currently bound to this student (e.g. they got a new phone, or a
    binding was created by mistake) so the next login from any device rebinds fresh. Never
    deletes the row — only marks it REVOKED, preserving audit history. Returns how many
    bindings were revoked."""
    if db.get(StudentProfile, student_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")

    bindings = db.query(DeviceBinding).filter(
        DeviceBinding.student_id == student_id, DeviceBinding.status == DeviceBindingStatus.ACTIVE
    ).all()
    now = utcnow()
    for binding in bindings:
        binding.status = DeviceBindingStatus.REVOKED
        binding.revoked_at = now
        binding.revoked_by_user_id = revoked_by_user_id
        binding.revocation_reason = reason
    db.commit()
    return len(bindings)
