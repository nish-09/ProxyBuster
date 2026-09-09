import uuid

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.models.security import Cooldown


def get_active_cooldown(db: Session, student_profile_id: uuid.UUID) -> Cooldown | None:
    # Compare in Python (not SQL) so this works identically whether the DB round-trips
    # timezone-aware datetimes (Postgres) or strips tzinfo (SQLite, used in tests).
    now = utcnow()
    candidates = (
        db.query(Cooldown)
        .filter(Cooldown.student_id == student_profile_id)
        .order_by(Cooldown.expires_at.desc())
        .limit(5)
        .all()
    )
    for c in candidates:
        if ensure_utc(c.expires_at) > now:
            return c
    return None
