import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.attendance import AttendanceStatus, SessionStatus


class AttendanceSessionCreate(BaseModel):
    lecture_id: uuid.UUID


class AttendanceSessionOut(BaseModel):
    id: uuid.UUID
    lecture_id: uuid.UUID
    professor_id: uuid.UUID
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}


class ScanRequest(BaseModel):
    token: str = Field(min_length=1, max_length=2000)


class ScanResult(BaseModel):
    status: Literal["marked", "rejected"]
    attendance_status: str | None = None
    message: str


class ManualAttendanceRequest(BaseModel):
    student_id: uuid.UUID
    lecture_id: uuid.UUID
    status: Literal["present", "absent", "late"]
    reason: str = Field(min_length=3, max_length=500)


class ManualAttendanceOut(BaseModel):
    id: uuid.UUID
    attendance_record_id: uuid.UUID
    professor_id: uuid.UUID
    reason: str
    previous_status: str | None
    new_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LiveFeedEntry(BaseModel):
    id: uuid.UUID
    student_name: str
    roll_number: str
    status: AttendanceStatus
    marked_at: datetime


class LiveSessionState(BaseModel):
    session_id: uuid.UUID
    status: SessionStatus
    present_count: int
    total_enrolled: int
    current_token_expires_at: datetime | None
    qr_payload: str | None = None
    feed: list[LiveFeedEntry] = []
