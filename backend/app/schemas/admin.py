from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.domain.enums import UserRole


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
    email: EmailStr
    role: UserRole
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRead]
    total: int
    skip: int
    limit: int
