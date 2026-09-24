import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.verification import DetectionStatus, DiscrepancyType, VerificationStatus, ViolationStatus


class ClassroomVerificationOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    lecture_id: uuid.UUID
    status: VerificationStatus
    image_count: int
    provider: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class VerificationResultOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    full_name: str
    roll_number: str
    qr_present: bool
    ai_status: DetectionStatus
    confidence: float
    discrepancy_type: DiscrepancyType
    decision_action: str | None = None
    decision_notes: str | None = None
    decided_at: datetime | None = None


class ClassroomVerificationDetailOut(BaseModel):
    verification: ClassroomVerificationOut
    total_enrolled: int
    students_excluded_no_reference_photo: int
    present_count: int
    confirmed_count: int
    discrepancy_count: int
    results: list[VerificationResultOut]


DecisionActionLiteral = Literal["confirmed_present", "asked_to_scan", "dismissed", "violation"]
ViolationReasonLiteral = Literal["proxy_attendance", "not_physically_present", "unauthorized_attendance", "other"]
RestrictionDurationLiteral = Literal["one_lecture", "one_day", "three_days", "seven_days", "custom"]


class VerificationDecisionRequest(BaseModel):
    action: DecisionActionLiteral
    notes: str | None = Field(default=None, max_length=500)
    # Required only when action == "violation":
    reason: ViolationReasonLiteral | None = None
    restriction_duration: RestrictionDurationLiteral | None = None
    custom_restriction_end: datetime | None = None

    @model_validator(mode="after")
    def _violation_requires_fields(self) -> "VerificationDecisionRequest":
        if self.action == "violation":
            if self.reason is None:
                raise ValueError("reason is required when action is 'violation'")
            if self.restriction_duration is None:
                raise ValueError("restriction_duration is required when action is 'violation'")
            if self.restriction_duration == "custom" and self.custom_restriction_end is None:
                raise ValueError("custom_restriction_end is required when restriction_duration is 'custom'")
        return self


class VerificationDecisionOut(BaseModel):
    result_id: uuid.UUID
    action: str
    notes: str | None
    created_at: datetime
    violation_id: uuid.UUID | None = None
    restriction_end: datetime | None = None


class ViolationOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    full_name: str
    roll_number: str
    lecture_id: uuid.UUID
    professor_id: uuid.UUID
    reason: str
    notes: str | None
    status: ViolationStatus
    created_at: datetime
    restriction_start: datetime
    restriction_end: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = None


class RevokeViolationRequest(BaseModel):
    revocation_reason: str = Field(min_length=3, max_length=500)
