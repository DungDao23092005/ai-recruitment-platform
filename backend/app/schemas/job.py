import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.enums import JobStatus, JobType, WorkplaceType


class JobCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    company_id: uuid.UUID
    title: str
    description: str
    job_type: JobType
    workplace_type: WorkplaceType
    location: str | None = None
    status: JobStatus = JobStatus.DRAFT
    # Required skills - new field name
    required_skills: Annotated[list[str] | None, Field(default=None, description="Required skills for the job")] = None
    # Preferred skills - new field
    preferred_skills: Annotated[list[str] | None, Field(default=None, description="Preferred/nice-to-have skills")] = None
    # Experience requirement
    minimum_years_experience: Annotated[float | None, Field(default=None, ge=0, description="Minimum years of experience required")] = None
    # Education requirement
    education_level: Annotated[str | None, Field(default=None, max_length=255, description="Required education level")] = None
    # Backward compatibility: legacy skills field maps to required_skills
    skills: Annotated[list[str] | None, Field(default=None, description="Legacy field for required skills")] = None


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
    skills: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_years_experience: float | None = None
    education_level: str | None = None
    created_at: datetime
    updated_at: datetime


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: JobStatus | None = None
    job_type: JobType | None = None
    workplace_type: WorkplaceType | None = None
    location: str | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    minimum_years_experience: float | None = None
    education_level: str | None = None
    skills: list[str] | None = None


class JobStatusUpdate(BaseModel):
    status: JobStatus
