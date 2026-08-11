from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.enums import JobStatus, JobType, WorkplaceType
from app.domain.models.base import BaseDomainEntity


@dataclass(kw_only=True)
class Job(BaseDomainEntity):
    company_id: uuid.UUID
    title: str
    description: str
    status: JobStatus = JobStatus.DRAFT
    job_type: JobType
    workplace_type: WorkplaceType
    location: str = ""
