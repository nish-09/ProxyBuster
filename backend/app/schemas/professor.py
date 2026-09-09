import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.student import CooldownStatusOut, DeviceSessionOut, Standing


class ActiveSubjectOut(BaseModel):
    class_division_id: uuid.UUID
    subject_code: str
    subject_name: str
    division_name: str
    avg_pct: float
    has_active_session: bool


class UpcomingSessionOut(BaseModel):
    lecture_id: uuid.UUID
    class_division_id: uuid.UUID
    subject_name: str
    division_name: str
    room: str | None
    scheduled_start: datetime
    scheduled_end: datetime
    has_active_session: bool


class ActivityFeedItem(BaseModel):
    id: uuid.UUID
    type: str
    severity: str
    description: str
    created_at: datetime
    status: str


class ProfessorDashboardOut(BaseModel):
    today_classes_count: int
    total_students: int
    avg_attendance_pct: float
    suspicious_events_count: int
    students_below_threshold_count: int
    active_subjects: list[ActiveSubjectOut]
    upcoming_sessions: list[UpcomingSessionOut]
    activity_feed: list[ActivityFeedItem]


class StudentListItem(BaseModel):
    student_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    roll_number: str
    program: str
    semester: int
    overall_percentage: float
    standing: Standing


class StudentListOut(BaseModel):
    items: list[StudentListItem]
    total: int


class SecurityEventOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    student_name: str | None
    event_type: str
    description: str
    severity: str
    status: str
    created_at: datetime
    event_metadata: dict


class StudentDetailOut(BaseModel):
    student_id: uuid.UUID
    full_name: str
    email: str
    roll_number: str
    program: str
    semester: int
    overall_percentage: float
    standing: Standing
    active_device: DeviceSessionOut | None
    cooldown: CooldownStatusOut
    recent_security_events: list[SecurityEventOut]


class AttendanceSheetCell(BaseModel):
    status: str | None = None
    method: str | None = None


class AttendanceSheetRow(BaseModel):
    student_id: uuid.UUID
    full_name: str
    roll_number: str
    cells: dict[str, AttendanceSheetCell]
    avg_pct: float
    suspicious: bool
    suspicious_reason: str | None = None


class AttendanceSheetOut(BaseModel):
    dates: list[str]
    rows: list[AttendanceSheetRow]


class AnomalyScoreOut(BaseModel):
    student_id: uuid.UUID
    full_name: str
    roll_number: str
    score: float
    reasons: list[str]
    method: str
    computed_at: datetime


class CooldownListItem(BaseModel):
    student_id: uuid.UUID
    full_name: str
    roll_number: str
    expires_at: datetime
    remaining_seconds: int
    reason: str


class EventActionResult(BaseModel):
    status: Literal["ok"] = "ok"
