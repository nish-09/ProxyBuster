import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.types import GUID


class DeviceSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    LOGGED_OUT = "logged_out"
    REVOKED = "revoked"


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
