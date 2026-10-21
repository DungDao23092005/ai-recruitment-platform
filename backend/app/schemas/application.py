import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import ApplicationStatus
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.interview import CandidateInterviewRead, RecruiterInterviewRead
from app.schemas.resume import ResumeRead


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID


class CandidateProfileReadMinimal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
    title: str | None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    candidate: CandidateProfileReadMinimal | None = None


class ApplicationDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str | None = None
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    candidate: CandidateProfileReadMinimal | None = None
    resume: ResumeRead | None = None
    parsed_job: ParsedJobSchema | None = None
    interviews: list[RecruiterInterviewRead] = []


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationOfferResponse(BaseModel):
    action: Literal["accept", "decline"]
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ApplicationWithJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str | None = None
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    interviews: list[CandidateInterviewRead] = []
