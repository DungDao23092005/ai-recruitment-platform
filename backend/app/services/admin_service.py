from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import ApplicationStatus, UserRole
from app.models import Application, Company, Job, User
from app.repositories import (
    ApplicationRepository,
    CompanyRepository,
    JobRepository,
    UserRepository,
)
from app.schemas.admin import (
    AdminJobListParams,
    AdminJobListResponse,
    AdminJobRead,
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserRead,
    ApplicationStatusCounts,
)
from app.services.ai_matching_service import AIMatchingService


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

    async def list_users(
        self,
        skip: int,
        limit: int,
        search: str | None = None,
        role: UserRole | None = None,
    ) -> tuple[list[User], int]:
        """Return a page of users (including deactivated ones) and the total."""
        return await self.users.list_admin_users(
            skip=skip,
            limit=limit,
            search=search,
            role=role,
        )

    async def get_user(self, user_id: uuid.UUID) -> User:
        """Return a user for admin views, including deactivated users."""
        user = await self.users.get_admin_user(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        return user

    async def deactivate_user(self, user_id: uuid.UUID, reason: str, admin_id: uuid.UUID) -> User:
        """Lock a user account by setting is_active = False.

        Locked users cannot authenticate but their data is preserved.
        This differs from soft_delete which removes the user from active queries
        and allows email reuse.

        Args:
            user_id: The ID of the user to lock.
            reason: The reason for locking the account (required, max 500 chars).
            admin_id: The ID of the admin performing the lock.

        Raises:
            EntityNotFoundException: If user not found.
            ValueError: If reason is empty or exceeds 500 characters.
        """
        reason = reason.strip()
        if not reason:
            raise ValueError("Lock reason is required")
        if len(reason) > 500:
            raise ValueError("Lock reason must not exceed 500 characters")

        user = await self.users.get_admin_user(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        user.is_active = False
        user.lock_reason = reason
        user.locked_at = datetime.now(timezone.utc)
        user.locked_by = admin_id
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def activate_user(self, user_id: uuid.UUID) -> User:
        """Unlock a user account by setting is_active = True.

        Preserves lock audit fields (lock_reason, locked_at, locked_by)
        for moderation history.
        """
        user = await self.users.get_admin_user(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        user.is_active = True
        # Preserve lock_reason, locked_at, locked_by for audit trail
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user_id: uuid.UUID) -> User:
        """Soft-delete a user account with email anonymization.

        This operation:
        - Anonymizes the email to prevent reuse (deleted_{uuid}@anonymized.local)
        - Soft-deletes the user (is_deleted = True)
        - Preserves relational data according to existing architecture
        - Ensures deleted account cannot authenticate
        - Ensures PII is no longer exposed in normal admin/user flows
        - Cleans up Qdrant resume vector if the user is a candidate
        """
        user = await self.users.get_admin_user(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")

        # Check if user is a candidate with a primary resume before deletion
        candidate_id = None
        if user.candidate_profile is not None:
            # Check for primary resume
            from app.repositories import ResumeRepository
            from app.models import Resume
            from sqlalchemy import select
            resume_repo = ResumeRepository(self.session, Resume)
            primary_resume = await resume_repo.get_primary_by_candidate(user.candidate_profile.id)
            if primary_resume is not None:
                candidate_id = user.candidate_profile.id

        # Anonymize email
        user.email = f"deleted_{user.id}@anonymized.local"
        # Soft delete
        await self.users.soft_delete(user)
        await self.session.commit()
        await self.session.refresh(user)

        # Clean up Qdrant resume vector if user was a candidate with primary resume
        if candidate_id is not None:
            try:
                matching_service = AIMatchingService()
                await matching_service.delete_resume_vector(candidate_id)
            except Exception as e:
                # Log but don't fail the user deletion if Qdrant cleanup fails
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to delete Qdrant resume vector for candidate {candidate_id}: {e}"
                )

        return user

    async def list_companies(
        self,
        skip: int,
        limit: int,
        search: str | None = None,
    ) -> tuple[list[Company], int]:
        """Return a page of companies (including locked ones) and the total."""
        return await self.companies.list_admin_companies(
            skip=skip,
            limit=limit,
            search=search,
        )

    async def get_company(self, company_id: uuid.UUID) -> Company:
        """Return a company for admin views, including locked companies."""
        company = await self.companies.get_admin_company(company_id)
        if company is None:
            raise EntityNotFoundException(f"Company {company_id} not found")
        return company

    async def list_jobs(
        self,
        params: AdminJobListParams,
    ) -> tuple[list[Job], int]:
        """Return a page of jobs for admin (all non-deleted jobs) and the total count."""
        return await self.jobs.list_admin_jobs(
            skip=params.skip,
            limit=params.limit,
            search=params.search,
        )

    async def list_jobs(
        self,
        params: AdminJobListParams,
    ) -> tuple[list[Job], int]:
        """Return a page of jobs for admin (all non-deleted jobs) and the total count."""
        return await self.jobs.list_admin_jobs(
            skip=params.skip,
            limit=params.limit,
            search=params.search,
        )