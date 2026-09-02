from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.domain.enums import JobStatus, JobType, WorkplaceType
from app.models import Company, Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    async def list_active_jobs(self, skip: int = 0, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.status == JobStatus.PUBLISHED,
                Job.is_deleted == False,  # noqa: E712
            )
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_jobs_with_filters(
        self,
        skip: int = 0,
        limit: int = 10,
        keyword: str | None = None,
        workplace_type: WorkplaceType | None = None,
        job_type: JobType | None = None,
        location: str | None = None,
    ) -> tuple[list[Job], int]:
        """Return a page of published/active jobs with filters and total count."""
        # Build the base query with filters
        base_stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.status == JobStatus.PUBLISHED,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        count_stmt = select(func.count(Job.id)).where(
            Job.status == JobStatus.PUBLISHED,
            Job.is_deleted == False,  # noqa: E712
        )

        if keyword:
            search_filter = Job.title.ilike(f"%{keyword}%")
            base_stmt = base_stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        if workplace_type:
            base_stmt = base_stmt.where(Job.workplace_type == workplace_type)
            count_stmt = count_stmt.where(Job.workplace_type == workplace_type)

        if job_type:
            base_stmt = base_stmt.where(Job.job_type == job_type)
            count_stmt = count_stmt.where(Job.job_type == job_type)

        if location:
            location_filter = Job.location.ilike(f"%{location}%")
            base_stmt = base_stmt.where(location_filter)
            count_stmt = count_stmt.where(location_filter)

        # Get total count
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        # Get paginated items
        base_stmt = base_stmt.order_by(Job.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(base_stmt)
        items = list(result.scalars().unique().all())

        return items, total

    async def list_jobs_by_company(
        self,
        company_id: Any,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.company_id == company_id,
                Job.is_deleted == False,  # noqa: E712
            )
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_jobs(self, skip: int = 0, limit: int = 10) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(Job.is_deleted == False)  # noqa: E712
            .order_by(Job.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_job_with_company(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_with_skills(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.skills))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_with_company_and_skills(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.company), joinedload(Job.skills))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_with_company_and_recruiters(self, job_id: Any) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.company).joinedload(Company.recruiters))
            .where(
                Job.id == job_id,
                Job.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def get_job_counts_by_status(self, company_id: Any) -> list[dict[str, Any]]:
        stmt = (
            select(Job.status, func.count(Job.id))
            .where(
                Job.company_id == company_id,
                Job.is_deleted == False,  # noqa: E712
            )
            .group_by(Job.status)
        )
        result = await self.session.execute(stmt)
        return [{"status": row[0].value, "count": row[1]} for row in result.all()]

    async def list_admin_jobs(
        self,
        skip: int = 0,
        limit: int = 10,
        search: str | None = None,
    ) -> tuple[list[Job], int]:
        """Return a page of jobs for admin (all jobs, not deleted) and the total count."""
        # Build the base query with filters
        base_stmt = select(Job).options(joinedload(Job.company)).where(Job.is_deleted == False)  # noqa: E712
        count_stmt = select(func.count(Job.id)).where(Job.is_deleted == False)  # noqa: E712

        if search:
            search_filter = Job.title.ilike(f"%{search}%")
            base_stmt = base_stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        # Get total count
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        # Get paginated items
        base_stmt = base_stmt.order_by(Job.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(base_stmt)
        items = list(result.scalars().unique().all())

        return items, total

    async def count_matching_jobs(
        self,
        user_role: str,
        actor_user_id: Any,
        employment_type: JobType | None = None,
        location: str | None = None,
        remote_only: bool = False,
    ) -> int:
        """Count jobs matching the given filters with authorization.

        Args:
            user_role: Role of the user (ADMIN, RECRUITER, CANDIDATE)
            actor_user_id: ID of the user making the request
            employment_type: Optional filter by job type
            location: Optional location filter (normalized)
            remote_only: Optional filter for remote-only jobs

        Returns:
            Total count of matching jobs
        """
        from app.models import RecruiterProfile

        filters = [Job.is_deleted == False]  # noqa: E712

        if user_role == "ADMIN":
            pass
        elif user_role == "RECRUITER":
            stmt = select(RecruiterProfile.company_id).where(
                RecruiterProfile.user_id == actor_user_id,
                RecruiterProfile.is_deleted == False,  # noqa: E712
            )
            result = await self.session.execute(stmt)
            recruiter_company_id = result.scalar_one_or_none()
            if recruiter_company_id is None:
                return 0
            filters.append(Job.company_id == recruiter_company_id)
        else:
            filters.append(Job.status == JobStatus.PUBLISHED)

        if employment_type:
            filters.append(Job.job_type == employment_type)

        if location:
            filters.append(Job.location.ilike(f"%{location}%"))

        if remote_only:
            filters.append(Job.workplace_type == WorkplaceType.REMOTE)

        count_stmt = select(func.count(Job.id)).where(*filters)
        total_result = await self.session.execute(count_stmt)
        return total_result.scalar_one()

    async def get_matching_jobs(
        self,
        user_role: str,
        actor_user_id: Any,
        employment_type: JobType | None = None,
        location: str | None = None,
        remote_only: bool = False,
        limit: int | None = None,
    ) -> list[Job]:
        """Get jobs matching the given filters with authorization.

        Args:
            user_role: Role of the user (ADMIN, RECRUITER, CANDIDATE)
            actor_user_id: ID of the user making the request
            employment_type: Optional filter by job type
            location: Optional location filter (normalized)
            remote_only: Optional filter for remote-only jobs
            limit: Optional limit for number of jobs to fetch (None for no limit)

        Returns:
            List of matching jobs with skills and company loaded
        """
        from app.models import RecruiterProfile

        filters = [Job.is_deleted == False]  # noqa: E712

        if user_role == "ADMIN":
            pass
        elif user_role == "RECRUITER":
            stmt = select(RecruiterProfile.company_id).where(
                RecruiterProfile.user_id == actor_user_id,
                RecruiterProfile.is_deleted == False,  # noqa: E712
            )
            result = await self.session.execute(stmt)
            recruiter_company_id = result.scalar_one_or_none()
            if recruiter_company_id is None:
                return []
            filters.append(Job.company_id == recruiter_company_id)
        else:
            filters.append(Job.status == JobStatus.PUBLISHED)

        if employment_type:
            filters.append(Job.job_type == employment_type)

        if location:
            filters.append(Job.location.ilike(f"%{location}%"))

        if remote_only:
            filters.append(Job.workplace_type == WorkplaceType.REMOTE)

        stmt = (
            select(Job)
            .options(selectinload(Job.skills), selectinload(Job.company))
            .where(*filters)
            .order_by(Job.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())