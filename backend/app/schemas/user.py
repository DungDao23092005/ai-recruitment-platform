import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.CANDIDATE


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CandidateProfileCreate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    title: str | None = None


class CandidateProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    title: str | None = None


class CandidateProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None
    phone: str | None
    title: str | None


class RecruiterProfileCreate(BaseModel):
    full_name: str | None = None
    position: str | None = None
    company_id: uuid.UUID | None = None


class RecruiterProfileUpdate(BaseModel):
    full_name: str | None = None
    position: str | None = None
    company_id: uuid.UUID | None = None


class RecruiterProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID | None
    full_name: str | None
    position: str | None
