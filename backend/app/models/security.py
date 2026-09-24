import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.types import GUID


class DeviceSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    LOGGED_OUT = "logged_out"
    REVOKED = "revoked"


class DeviceBindingStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class DeviceBinding(Base):
    """Ties a client-reported `device_id` to the one student who first logged in from it —
    an anti-proxy-sharing layer, not real hardware attestation (the id is a random value the
    client itself generates and stores in localStorage; clearing it or using another browser
    creates a fresh, unbound device_id). Prevents a DIFFERENT student from claiming an
    already-bound device; deliberately does NOT restrict how many devices one student can bind
    (e.g. a phone and a laptop) — that isn't a proxy risk, only device *sharing* is. Enforced at
    login (see auth_service.login_user), not at scan, because the current ScanRequest carries no
    device identity — see app/schemas/attendance.py.

    Every row is kept (never deleted) for audit history; only one ACTIVE row per device_id is
    allowed at a time (partial unique index below), mirroring the
    uq_active_session_per_lecture pattern already used for attendance sessions."""

    __tablename__ = "device_bindings"
    __table_args__ = (
        Index(
            "uq_active_device_binding",
            "device_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    status: Mapped[DeviceBindingStatus] = mapped_column(
        Enum(DeviceBindingStatus, name="device_binding_status"), default=DeviceBindingStatus.ACTIVE, nullable=False
    )
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SecurityEventStatus(str, enum.Enum):
    OPEN = "open"
    FLAGGED = "flagged"
    DISMISSED = "dismissed"


class SecurityEventSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DeviceSession(Base):
    __tablename__ = "device_sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # JWT jti
    device_id: Mapped[str] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=True)
    login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    logout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DeviceSessionStatus] = mapped_column(
        Enum(DeviceSessionStatus, name="device_session_status"), default=DeviceSessionStatus.ACTIVE, nullable=False
    )


class Cooldown(Base):
    __tablename__ = "cooldowns"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="manual_logout", nullable=False)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    severity: Mapped[SecurityEventSeverity] = mapped_column(
        Enum(SecurityEventSeverity, name="security_event_severity"), default=SecurityEventSeverity.LOW
    )
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[SecurityEventStatus] = mapped_column(
        Enum(SecurityEventStatus, name="security_event_status"), default=SecurityEventStatus.OPEN
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnomalyScore(Base):
    __tablename__ = "anomaly_scores"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # 0-100
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(20), default="rule_based", nullable=False)  # rule_based | ml
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
