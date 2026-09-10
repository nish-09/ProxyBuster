import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.validation import EmailStr
from app.models.user import UserRole


# ---------- Students ----------


class AdminCreateStudentRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    roll_number: str = Field(min_length=1, max_length=50)
    program: str = Field(min_length=1, max_length=255)
    semester: int = Field(ge=1, le=12)


class AdminUpdateStudentRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    program: str | None = Field(default=None, min_length=1, max_length=255)
    semester: int | None = Field(default=None, ge=1, le=12)
    is_active: bool | None = None


class AdminStudentOut(BaseModel):
    id: uuid.UUID  # student_profile id
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    roll_number: str
    program: str
    semester: int
    created_at: datetime


# ---------- Professors ----------


class AdminCreateProfessorRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    department: str = Field(min_length=1, max_length=255)


class AdminUpdateProfessorRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class AdminProfessorOut(BaseModel):
    id: uuid.UUID  # professor_profile id
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    department: str
    created_at: datetime


# ---------- Subjects ----------


class AdminCreateSubjectRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    credits: int = Field(default=3, ge=1, le=12)


class AdminUpdateSubjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    credits: int | None = Field(default=None, ge=1, le=12)


class AdminSubjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    credits: int

    model_config = {"from_attributes": True}


# ---------- Class divisions ----------


class AdminCreateDivisionRequest(BaseModel):
    subject_id: uuid.UUID
    professor_id: uuid.UUID  # professor_profile id
    name: str = Field(min_length=1, max_length=50)
    semester: int = Field(ge=1, le=12)
    room: str | None = Field(default=None, max_length=50)


class AdminUpdateDivisionRequest(BaseModel):
    professor_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=50)
    semester: int | None = Field(default=None, ge=1, le=12)
    room: str | None = Field(default=None, max_length=50)


class AdminDivisionOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    professor_id: uuid.UUID
    professor_name: str
    name: str
    semester: int
    room: str | None
    enrolled_count: int


# ---------- Enrollments ----------


class AdminCreateEnrollmentRequest(BaseModel):
    student_id: uuid.UUID  # student_profile id
    class_division_id: uuid.UUID


class AdminBulkEnrollRequest(BaseModel):
    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    class_division_id: uuid.UUID


class AdminBulkEnrollResult(BaseModel):
    enrolled: list[uuid.UUID]
    already_enrolled: list[uuid.UUID]
    not_found: list[uuid.UUID]


class AdminEnrollmentOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    roll_number: str
    class_division_id: uuid.UUID
    created_at: datetime


# ---------- Lectures ----------


class AdminCreateLectureRequest(BaseModel):
    class_division_id: uuid.UUID
    topic: str | None = Field(default=None, max_length=255)
    scheduled_start: datetime
    scheduled_end: datetime
    room: str | None = Field(default=None, max_length=50)


class AdminUpdateLectureRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=255)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    room: str | None = Field(default=None, max_length=50)


class AdminLectureOut(BaseModel):
    id: uuid.UUID
    class_division_id: uuid.UUID
    subject_name: str
    division_name: str
    topic: str | None
    scheduled_start: datetime
    scheduled_end: datetime
    room: str | None


class AdminUserRoleOut(BaseModel):
    role: UserRole
