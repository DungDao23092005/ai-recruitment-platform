import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ApplicationStatus


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
