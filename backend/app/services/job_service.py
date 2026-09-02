from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, InvalidTransitionException
from app.domain.enums import JobStatus, UserRole
from app.models import Company, Job, User
from app.repositories import CompanyRepository, JobRepository
from app.schemas.job import JobCreate, JobUpdate
from app.services.user_service import UserService

JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.DRAFT: {JobStatus.PUBLISHED},
    JobStatus.PUBLISHED: {JobStatus.CLOSED},
    JobStatus.CLOSED: {JobStatus.PUBLISHED},
    JobStatus.EXPIRED: set(),
}


class JobService:
    def __init__(
        self,
        session: AsyncSession,
        embedding_service=None,
        vector_repository=None,
    ) -> None:
        from app.ai.embeddings.embedding_service import (
            EmbeddingService,
            SentenceTransformerEmbeddingProvider,
        )
        from app.ai.vector_db.qdrant_client import QdrantVectorRepository

        self.session = session
        self.jobs = JobRepository(session, Job)
        self.companies = CompanyRepository(session, Company)
        self.embedding_service = embedding_service or EmbeddingService(
            SentenceTransformerEmbeddingProvider()
        )
        self.vector_repository = vector_repository or QdrantVectorRepository()

    async def create_job(self, data: JobCreate) -> Job:
        company = await self.companies.get_by_id(data.company_id)
        if company is None:
            raise EntityNotFoundException(f"Company {data.company_id} not found")

        job = Job(
            company_id=data.company_id,
            title=data.title,
            description=data.description,
            status=data.status,
            job_type=data.job_type,
            workplace_type=data.workplace_type,
            location=data.location or "",
        )
        self.session.add(job)
        try:
            await self.session.flush()  # Get the job ID before adding skills
            await self._attach_skills(job, data.skills)
            await self._reindex_job(job)
            await self.session.commit()
            await self.session.refresh(job)
            # Explicitly load company relationship AFTER refresh for response serialization
            await job.awaitable_attrs.company
        except Exception:
            await self.session.rollback()
            raise
        return job

    async def publish_job(self, job_id: uuid.UUID) -> Job:
        return await self.update_job_status(job_id, JobStatus.PUBLISHED)

    async def close_job(self, job_id: uuid.UUID) -> Job:
        return await self.update_job_status(job_id, JobStatus.CLOSED)

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        new_status: JobStatus,
    ) -> Job:
        job = await self.jobs.get_job_with_company_and_skills(job_id)
        if job is None:
            raise EntityNotFoundException(f"Job {job_id} not found")
        allowed = JOB_TRANSITIONS.get(job.status, set())
        if new_status not in allowed:
            raise InvalidTransitionException(
                f"Cannot change job status from {job.status.value!r} "
                f"to {new_status.value!r}"
            )
        job.status = new_status
        await self._commit_and_refresh(job)
        return job

    async def update_job(
        self,
        user: User,
        job_id: uuid.UUID,
        data: JobUpdate,
    ) -> Job:
        """Update editable job fields with ownership enforced.

        Ownership is resolved through ``get_recruiter_job_by_id`` (admin may
        manage any job; a recruiter only their own company's jobs). The
        ``status`` field is intentionally ignored here so status can only
        change through ``update_job_status`` and the domain state machine.
        Searchable content is re-embedded and the Qdrant job vector is
        upserted before the SQL commit; any failure rolls back SQL so the
        caller is never silently reported success.
        """
        job = await self.get_recruiter_job_by_id(user, job_id)
        has_changes = False
        if data.title is not None and data.title.strip() != job.title:
            job.title = data.title.strip()
            has_changes = True
        if data.description is not None and data.description.strip() != job.description:
            job.description = data.description.strip()
            has_changes = True
        if data.job_type is not None and data.job_type != job.job_type:
            job.job_type = data.job_type
            has_changes = True
        if data.workplace_type is not None and data.workplace_type != job.workplace_type:
            job.workplace_type = data.workplace_type
            has_changes = True
        if data.location is not None and data.location.strip() != job.location:
            job.location = data.location.strip()
            has_changes = True
        if not has_changes and data.skills is None:
            return job
        try:
            if data.skills is not None:
                await self._attach_skills(job, data.skills)
            if has_changes:
                await self._reindex_job(job)
            await self._commit_and_refresh(job)
        except Exception:
            await self.session.rollback()
            raise
        return job

    async def delete_job(
        self,
        user: User,
        job_id: uuid.UUID,
    ) -> None:
        """Soft delete a job with ownership enforced.

        The SQL row is flagged ``is_deleted`` and never hard deleted; the
        matching Qdrant job vector is removed. Applications are preserved.
        """
        job = await self.get_recruiter_job_by_id(user, job_id)
        job.is_deleted = True
        try:
            await self.vector_repository.delete_vector("jobs", job.id)
            await self._commit_and_refresh(job)
        except Exception:
            await self.session.rollback()
            raise

    @staticmethod
    def _canonical_job_text(job: Job) -> str:
        return (
            f"Job Title: {job.title}\n"
            f"Description: {job.description}\n"
            f"Location: {job.location}"
        )

    async def _reindex_job(self, job: Job) -> None:
        text = self._canonical_job_text(job)
        vector = await self.embedding_service.embed_text(text)
        # Explicitly load skills relationship to avoid implicit lazy loading
        skills = await job.awaitable_attrs.skills
        skills_list = [skill.name for skill in skills] if skills else []
        await self.vector_repository.upsert_job_vector(
            job_id=job.id,
            vector=vector,
            skills=skills_list,
            created_at=job.created_at,
        )

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        return await self.jobs.list_active_jobs(skip=skip, limit=limit)

    async def list_public_jobs(
        self,
        skip: int = 0,
        limit: int = 10,
        keyword: str | None = None,
        workplace_type: WorkplaceType | None = None,
        job_type: JobType | None = None,
        location: str | None = None,
    ) -> tuple[list[Job], int]:
        """List published/active jobs with filters for public job board.

        Returns (items, total_count).
        """
        return await self.jobs.list_active_jobs_with_filters(
            skip=skip,
            limit=limit,
            keyword=keyword,
            workplace_type=workplace_type,
            job_type=job_type,
            location=location,
        )

    async def list_recruiter_jobs(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        owned_company_id = await self._get_owned_company_id(user_id)
        if owned_company_id is None:
            return []
        return await self.jobs.list_jobs_by_company(
            owned_company_id,
            skip=skip,
            limit=limit,
        )

    async def get_recruiter_job_by_id(
        self,
        user: User,
        job_id: uuid.UUID,
    ) -> Job:
        """Resolve a job for a recruiter/admin with ownership enforced.

        Admin can access any job (all statuses). A recruiter may only access
        jobs belonging to the company they own. Raises
        ``EntityNotFoundException`` for missing, soft-deleted, or unowned jobs
        so existence is never leaked to other recruiters.
        """
        job = await self.jobs.get_job_with_company_and_skills(job_id)
        if job is None:
            raise EntityNotFoundException(f"Job {job_id} not found")

        if user.role == UserRole.ADMIN:
            return job

        owned_company_id = await self._get_owned_company_id(user.id)
        if owned_company_id is None or owned_company_id != job.company_id:
            raise EntityNotFoundException(f"Job {job_id} not found")
        return job

    async def _get_owned_company_id(
        self,
        user_id: uuid.UUID,
    ) -> uuid.UUID | None:
        user = await UserService(self.session).get_user_with_profile(user_id)
        profile = user.recruiter_profile if user is not None else None
        return profile.company_id if profile is not None else None

    async def list_all_jobs(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> list[Job]:
        return await self.jobs.list_all_jobs(skip=skip, limit=limit)

    async def _commit_and_refresh(self, entity) -> None:
        try:
            await self.session.commit()
            await self.session.refresh(entity)
        except Exception:
            await self.session.rollback()
            raise

    async def _attach_skills(self, job: Job, skill_names: list[str]) -> None:
        """Attach skills to a job, creating new skills if they don't exist.

        Deduplicates skill names case-insensitively before attaching to prevent
        duplicate Skill relationships and SQL Server IntegrityError.

        Validates skill name length (max 100 chars) to prevent SQL truncation errors.
        """
        from app.core.exceptions import ValidationError
        from app.models import Skill
        from sqlalchemy import select

        MAX_SKILL_NAME_LENGTH = 100

        # Explicitly load skills relationship to avoid implicit lazy loading
        await job.awaitable_attrs.skills

        # Clear existing skills
        job.skills.clear()

        # Deduplicate skills case-insensitively, preserving first occurrence's canonical spelling
        seen: set[str] = set()
        unique_skill_names: list[str] = []

        for skill_name in skill_names:
            stripped = skill_name.strip()
            if not stripped:
                continue
            if len(stripped) > MAX_SKILL_NAME_LENGTH:
                raise ValidationError(
                    f"Skill name exceeds maximum length of {MAX_SKILL_NAME_LENGTH} characters: {stripped!r}"
                )
            key = stripped.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_skill_names.append(stripped)

        for skill_name in unique_skill_names:
            # Find existing skill (case-insensitive)
            stmt = select(Skill).where(Skill.name.ilike(skill_name))
            result = await self.session.execute(stmt)
            skill = result.scalars().first()
            if skill is None:
                # Create new skill
                skill = Skill(name=skill_name)
                self.session.add(skill)
                await self.session.flush()
            job.skills.append(skill)