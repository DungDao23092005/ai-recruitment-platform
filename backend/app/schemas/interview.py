from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class InterviewType(str):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    HR = "hr"
    CASE_STUDY = "case_study"


class InterviewStatus(str):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InterviewBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    interview_type: str = Field(default="technical")
    meeting_url: HttpUrl | None = None
    location: str | None = None
    notes: str | None = None
    status: str = Field(default="scheduled")


class InterviewCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    interview_type: str = Field(default="technical")
    meeting_url: HttpUrl | None = None
    location: str | None = None
    notes: str | None = None


class InterviewUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    interview_type: str | None = None
    meeting_url: HttpUrl | None = None
    location: str | None = None
    notes: str | None = None
    status: str | None = None


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    interview_type: str
    meeting_url: str | None = None
    location: str | None = None
    notes: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime