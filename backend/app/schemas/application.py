import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ApplicationStatus
from app.schemas.ai_job import ParsedJobSchema
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


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationWithJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str | None = None
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
