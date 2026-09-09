import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole
    # student-only
    roll_number: str | None = None
    program: str | None = None
    semester: int | None = None
    # professor-only
    department: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_id: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: uuid.UUID


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole

    model_config = {"from_attributes": True}
