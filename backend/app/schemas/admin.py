from __future__ import annotations

from pydantic import BaseModel


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
