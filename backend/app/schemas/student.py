import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Standing = Literal["good", "warning"]


class SubjectAttendanceOut(BaseModel):
    class_division_id: uuid.UUID
    subject_code: str
    subject_name: str
    division_name: str
    present: int
    late: int
    manual: int
    absent: int
    total: int
    percentage: float
    classes_can_miss: int
    classes_needed_to_recover: int
    next_class_at: datetime | None = None


class TodayScheduleItem(BaseModel):
    class_division_id: uuid.UUID
    subject_name: str
    room: str | None
    scheduled_start: datetime
    scheduled_end: datetime
    state: Literal["past", "current", "upcoming"]


class StudentDashboardOut(BaseModel):
    full_name: str
    roll_number: str
    program: str
    semester: int
    overall_percentage: float
    total_classes: int
    attended_classes: int
    standing: Standing
    subjects: list[SubjectAttendanceOut]
    today_schedule: list[TodayScheduleItem]


class AttendanceHistoryEntry(BaseModel):
    id: uuid.UUID
    lecture_id: uuid.UUID
    subject_name: str
    professor_name: str
    status: str
    method: str
    marked_at: datetime | None
    scheduled_start: datetime


class AttendanceHistoryOut(BaseModel):
    entries: list[AttendanceHistoryEntry]
    present: int
    absent: int
    late: int
    manual: int
    total: int
    percentage: float


class CooldownStatusOut(BaseModel):
    active: bool
    remaining_seconds: int
    expires_at: datetime | None = None


class DeviceSessionOut(BaseModel):
    device_id: str | None
    ip_address: str | None
    user_agent: str | None
    login_at: datetime
    logout_at: datetime | None = None
    status: str

    model_config = {"from_attributes": True}


class BunkCalculatorRequest(BaseModel):
    class_division_id: uuid.UUID
    required_pct: float = Field(default=75.0, ge=0, le=100)


class BunkCalculatorOut(BaseModel):
    current_percentage: float
    classes_can_miss: int
    classes_needed_to_recover: int
    projected_after_attending_1: float
    projected_after_missing_1: float
