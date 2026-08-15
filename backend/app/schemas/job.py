import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import JobStatus, JobType, WorkplaceType


class JobCreate(BaseModel):
    company_id: uuid.UUID
    title: str
    description: str
    job_type: JobType
    workplace_type: WorkplaceType
    location: str | None = None
    status: JobStatus = JobStatus.DRAFT


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str | None = None
    title: str
    description: str
    status: JobStatus
    job_type: JobType
    workplace_type: WorkplaceType
    location: str
    created_at: datetime
    updated_at: datetime


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: JobStatus | None = None
    job_type: JobType | None = None
    workplace_type: WorkplaceType | None = None
    location: str | None = None
