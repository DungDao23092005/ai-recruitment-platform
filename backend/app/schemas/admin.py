from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CompanySize, JobStatus, JobType, UserRole, WorkplaceType


class ApplicationStatusCounts(BaseModel):
    applied: int = 0
    under_review: int = 0
    shortlisted: int = 0
    interviewing: int = 0
    accepted: int = 0
    rejected: int = 0
    withdrawn: int = 0


class AdminStatsResponse(BaseModel):
    total_users: int
    total_candidates: int
    total_recruiters: int
    total_admins: int
    total_companies: int
    total_jobs: int
    total_applications: int
    applications_by_status: ApplicationStatusCounts


class AdminUserRead(BaseModel):
    """Admin-facing view of a user.

    Deliberately excludes ``password_hash`` and any other secret fields.
    ``is_deleted`` is exposed so admins can distinguish active users from
    deactivated (soft-deleted) ones.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    is_deleted: bool
    lock_reason: str | None = None
    locked_at: datetime | None = None
    locked_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRead]
    total: int
    skip: int
    limit: int


class AdminCompanyRead(BaseModel):
    """Admin-facing view of a company.

    ``is_deleted`` is exposed so admins can distinguish active companies
    from locked (soft-deleted) ones. No company status field exists by
    design; the active/locked state is derived from ``is_deleted``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    tax_code: str
    size: CompanySize
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class AdminCompanyListResponse(BaseModel):
    items: list[AdminCompanyRead]
    total: int
    skip: int
    limit: int


class AdminJobRead(BaseModel):
    """Admin-facing view of a job."""

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


class AdminJobListParams(BaseModel):
    skip: int = 0
    limit: int = 10
    search: str | None = None


class AdminJobListResponse(BaseModel):
    items: list[AdminJobRead]
    total: int
    skip: int
    limit: int
