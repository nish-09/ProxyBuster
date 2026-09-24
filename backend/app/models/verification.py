import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.types import GUID


class StudentReferencePhoto(Base):
    """One reference photo per student, used ONLY server-side so the classroom verification AI
    provider can match a face in a classroom photo to a known student. Kept in its own table
    (not a column on StudentProfile) so ordinary StudentProfile queries never pull image bytes
    off the wire."""

    __tablename__ = "student_reference_photos"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VerificationStatus(str, enum.Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DetectionStatus(str, enum.Enum):
    """AI's per-student read of a classroom photo set, after this system's own confidence
    thresholding (see app/services/verification/service.py) — never trusted raw from the
    provider."""

    CONFIRMED = "confirmed"
    HIGH_CONFIDENCE = "high_confidence"
    UNCERTAIN = "uncertain"
    NOT_DETECTED = "not_detected"


class DiscrepancyType(str, enum.Enum):
    ATTENDED_AND_DETECTED = "attended_and_detected"
    ATTENDED_NOT_DETECTED = "attended_not_detected"
    DETECTED_NOT_ATTENDED = "detected_not_attended"
    NONE = "none"  # QR absent AND AI didn't see them either — nothing to review


class ClassroomVerification(Base):
    """One 'Verify Classroom' action by a professor: 1-3 photos submitted, analyzed once, and
    compared against that lecture's QR attendance. See app/services/verification/service.py."""

    __tablename__ = "classroom_verifications"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("attendance_sessions.id"), nullable=False, index=True
    )
    lecture_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("lectures.id"), nullable=False, index=True)
    professor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("professor_profiles.id"), nullable=False, index=True
    )
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"), default=VerificationStatus.PROCESSING, nullable=False
    )
    image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # Safe-to-display summary only (e.g. "Analysis failed. Please try again.") — never the raw
    # provider response/exception text, which could echo back request internals.
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list["ClassroomVerificationResult"]] = relationship(
        back_populates="verification", cascade="all, delete-orphan"
    )


class ClassroomVerificationResult(Base):
    """One row per enrolled-and-photographed student for a given verification: what the AI
    reported, what QR attendance already showed, and the discrepancy classification the
    comparison engine derived from the two. This — not the AI's raw output — is what the
    professor reviews and acts on."""

    __tablename__ = "classroom_verification_results"
    __table_args__ = (UniqueConstraint("verification_id", "student_id", name="uq_verification_student"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    verification_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("classroom_verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    qr_present: Mapped[bool] = mapped_column(nullable=False)
    ai_status: Mapped[DetectionStatus] = mapped_column(Enum(DetectionStatus, name="detection_status"), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    discrepancy_type: Mapped[DiscrepancyType] = mapped_column(
        Enum(DiscrepancyType, name="discrepancy_type"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    verification: Mapped["ClassroomVerification"] = relationship(back_populates="results")
    decision: Mapped["VerificationDecision | None"] = relationship(
        back_populates="result", uselist=False, cascade="all, delete-orphan"
    )


class VerificationDecisionAction(str, enum.Enum):
    CONFIRMED_PRESENT = "confirmed_present"
    ASKED_TO_SCAN = "asked_to_scan"
    DISMISSED = "dismissed"
    VIOLATION = "violation"


class VerificationDecision(Base):
    """The professor's explicit call on one discrepancy row — the only thing in this feature
    that is ever allowed to touch attendance state or create a violation. AI evidence alone
    never does either (see app/services/verification/service.py::record_decision)."""

    __tablename__ = "verification_decisions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    result_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("classroom_verification_results.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("professor_profiles.id"), nullable=False)
    action: Mapped[VerificationDecisionAction] = mapped_column(
        Enum(VerificationDecisionAction, name="verification_decision_action"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    result: Mapped["ClassroomVerificationResult"] = relationship(back_populates="decision")


class ViolationReason(str, enum.Enum):
    PROXY_ATTENDANCE = "proxy_attendance"
    NOT_PHYSICALLY_PRESENT = "not_physically_present"
    UNAUTHORIZED_ATTENDANCE = "unauthorized_attendance"
    OTHER = "other"


class ViolationStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class AttendanceViolation(Base):
    """A professor-confirmed attendance violation. Doubles as the restriction record itself
    (restriction_start/end + status) rather than a separate table, to avoid duplicating
    student/session/professor data across two tables — see
    app/services/violation_service.py."""

    __tablename__ = "attendance_violations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    lecture_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("lectures.id"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("attendance_sessions.id"), nullable=True)
    professor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("professor_profiles.id"), nullable=False, index=True
    )
    verification_result_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("classroom_verification_results.id"), nullable=True
    )
    reason: Mapped[ViolationReason] = mapped_column(Enum(ViolationReason, name="violation_reason"), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ViolationStatus] = mapped_column(
        Enum(ViolationStatus, name="violation_status"), default=ViolationStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    restriction_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    restriction_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
