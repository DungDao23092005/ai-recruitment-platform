from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ApplicationStatus, UserRole
from app.models import Application, Company, Job, User
from app.repositories import (
    ApplicationRepository,
    CompanyRepository,
    JobRepository,
    UserRepository,
)
from app.schemas.admin import AdminStatsResponse, ApplicationStatusCounts


class AdminService:
    """Aggregate platform-wide statistics for the admin dashboard.

    Counts are computed from the database through the existing repository
    layer. Soft-deleted rows are excluded by the repository's list_all,
    which filters ``is_deleted == False`` for soft-deletable models.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session, User)
        self.companies = CompanyRepository(session, Company)
        self.jobs = JobRepository(session, Job)
        self.applications = ApplicationRepository(session, Application)

    async def get_stats(self) -> AdminStatsResponse:
        users = await self.users.list_all()
        companies = await self.companies.list_all()
        jobs = await self.jobs.list_all()
        applications = await self.applications.list_all()

        total_candidates = 0
        total_recruiters = 0
        total_admins = 0
        for user in users:
            if user.role == UserRole.CANDIDATE:
                total_candidates += 1
            elif user.role == UserRole.RECRUITER:
                total_recruiters += 1
            elif user.role == UserRole.ADMIN:
                total_admins += 1

        status_counts = {status: 0 for status in ApplicationStatus}
        for application in applications:
            status_counts[application.status] += 1

        return AdminStatsResponse(
            total_users=len(users),
            total_candidates=total_candidates,
            total_recruiters=total_recruiters,
            total_admins=total_admins,
            total_companies=len(companies),
            total_jobs=len(jobs),
            total_applications=len(applications),
            applications_by_status=ApplicationStatusCounts(
                applied=status_counts[ApplicationStatus.APPLIED],
                under_review=status_counts[ApplicationStatus.UNDER_REVIEW],
                shortlisted=status_counts[ApplicationStatus.SHORTLISTED],
                interviewing=status_counts[ApplicationStatus.INTERVIEWING],
                accepted=status_counts[ApplicationStatus.ACCEPTED],
                rejected=status_counts[ApplicationStatus.REJECTED],
                withdrawn=status_counts[ApplicationStatus.WITHDRAWN],
            ),
        )