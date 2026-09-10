import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.types import GUID


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    MANUAL = "manual"
    SUSPICIOUS = "suspicious"


class AttendanceMethod(str, enum.Enum):
    QR = "qr"
    MANUAL = "manual"


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        # Enforces "at most one active session per lecture" at the DB level (partial unique
        # index on lecture_id, scoped to ACTIVE rows) so a race between two concurrent
        # POST /attendance/sessions calls can't create two active sessions for one lecture —
        # the loser gets an IntegrityError instead of silently succeeding.
        Index(
            "uq_active_session_per_lecture",
            "lecture_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    lecture_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("lectures.id"), nullable=False)
    professor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("professor_profiles.id"), nullable=False
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"), default=SessionStatus.ACTIVE, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tokens: Mapped[list["AttendanceToken"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    records: Mapped[list["AttendanceRecord"]] = relationship(back_populates="session")


class AttendanceToken(Base):
    """A short-lived signed token representing one 10s QR rotation."""

    __tablename__ = "attendance_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("attendance_sessions.id"), nullable=False, index=True
    )
    nonce: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consumed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["AttendanceSession"] = relationship(back_populates="tokens")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("student_id", "lecture_id", name="uq_student_lecture"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False
    )
    lecture_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("lectures.id"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("attendance_sessions.id"), nullable=True
    )
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus, name="attendance_status"), nullable=False)
    method: Mapped[AttendanceMethod] = mapped_column(Enum(AttendanceMethod, name="attendance_method"), nullable=False)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["AttendanceSession | None"] = relationship(back_populates="records")
    manual_entry: Mapped["ManualAttendance | None"] = relationship(
        back_populates="attendance_record", uselist=False, cascade="all, delete-orphan"
    )


class ManualAttendance(Base):
    """Audit trail for every professor-initiated manual attendance action."""

    __tablename__ = "manual_attendance"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("attendance_records.id"), nullable=False
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("professor_profiles.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attendance_record: Mapped["AttendanceRecord"] = relationship(back_populates="manual_entry")
