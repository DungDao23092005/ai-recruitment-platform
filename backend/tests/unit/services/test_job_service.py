import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import JobStatus, JobType, WorkplaceType
from app.models import Company, Job
from app.repositories import CompanyRepository, JobRepository
from app.schemas.job import JobCreate, JobUpdate
from app.services.job_service import JobService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_company() -> Company:
    return Company(
        id=uuid.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        tax_code="123456789",
        size="startup",
    )


def make_job(
    job_id: uuid.UUID | None = None,
    status: JobStatus = JobStatus.DRAFT,
) -> Job:
    return Job(
        id=job_id or uuid.uuid4(),
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        description="Build APIs",
        status=status,
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
        location="",
    )


def make_service(session) -> JobService:
    service = JobService(session)
    service.jobs = AsyncMock(spec=JobRepository)
    service.companies = AsyncMock(spec=CompanyRepository)
    return service


def make_ai_service(session, embedding, vector_repository) -> JobService:
    service = JobService(
        session,
        embedding_service=embedding,
        vector_repository=vector_repository,
    )
    service.jobs = AsyncMock(spec=JobRepository)
    service.companies = AsyncMock(spec=CompanyRepository)
    return service


def make_ai_dependencies():
    embedding = MagicMock()
    embedding.embed_text = MagicMock(return_value=[0.0] * 4)
    vector_repository = MagicMock()
    vector_repository.upsert_job_vector = AsyncMock()
    vector_repository.delete_vector = AsyncMock()
    return embedding, vector_repository


class TestCreateJob:
    def test_creates_job(self):
        session = make_session()
        service = make_service(session)
        company = make_company()
        service.companies.get_by_id.return_value = company
        data = JobCreate(
            company_id=company.id,
            title="Backend Engineer",
            description="Build APIs",
            job_type=JobType.FULL_TIME,
            workplace_type=WorkplaceType.HYBRID,
            location="Ho Chi Minh",
        )

        job = asyncio.run(service.create_job(data))

        assert job.company_id == company.id
        assert job.title == "Backend Engineer"
        assert job.status == JobStatus.DRAFT
        assert job.location == "Ho Chi Minh"
        session.add.assert_called_once_with(job)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_defaults_location_to_empty_string(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_id.return_value = make_company()
        data = JobCreate(
            company_id=uuid.uuid4(),
            title="Data Engineer",
            description="Build pipelines",
            job_type=JobType.CONTRACT,
            workplace_type=WorkplaceType.ON_SITE,
        )

        job = asyncio.run(service.create_job(data))

        assert job.location == ""

    def test_company_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_id.return_value = None
        data = JobCreate(
            company_id=uuid.uuid4(),
            title="Backend Engineer",
            description="Build APIs",
            job_type=JobType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
        )

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.create_job(data))

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.companies.get_by_id.return_value = make_company()
        session.commit.side_effect = RuntimeError("db down")
        data = JobCreate(
            company_id=uuid.uuid4(),
            title="Backend Engineer",
            description="Build APIs",
            job_type=JobType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
        )

        with pytest.raises(RuntimeError):
            asyncio.run(service.create_job(data))

        session.rollback.assert_awaited_once()


class TestPublishJob:
    def test_publishes_draft(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.DRAFT)
        service.jobs.get_job_with_company_and_skills.return_value = job

        result = asyncio.run(service.publish_job(job.id))

        assert result is job
        assert job.status == JobStatus.PUBLISHED
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_job_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_job_with_company_and_skills.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.publish_job(uuid.uuid4()))

        session.commit.assert_not_awaited()

    def test_non_draft_raises_invalid_transition(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.PUBLISHED)
        service.jobs.get_job_with_company_and_skills.return_value = job

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.publish_job(job.id))

        session.commit.assert_not_awaited()


class TestCloseJob:
    def test_closes_published(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.PUBLISHED)
        service.jobs.get_job_with_company_and_skills.return_value = job

        result = asyncio.run(service.close_job(job.id))

        assert result is job
        assert job.status == JobStatus.CLOSED
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_job_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_job_with_company_and_skills.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.close_job(uuid.uuid4()))

        session.commit.assert_not_awaited()

    def test_non_published_raises_invalid_transition(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.DRAFT)
        service.jobs.get_job_with_company_and_skills.return_value = job

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.close_job(job.id))

        session.commit.assert_not_awaited()


class TestListJobs:
    def test_returns_active_jobs(self):
        session = make_session()
        service = make_service(session)
        jobs = [make_job(status=JobStatus.PUBLISHED) for _ in range(3)]
        service.jobs.list_active_jobs.return_value = jobs

        result = asyncio.run(service.list_jobs(skip=0, limit=10))

        assert result == jobs
        service.jobs.list_active_jobs.assert_awaited_once_with(skip=0, limit=10)


class TestUpdateJobStatus:
    def test_draft_to_published(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.DRAFT)
        service.jobs.get_job_with_company_and_skills.return_value = job

        result = asyncio.run(
            service.update_job_status(job.id, JobStatus.PUBLISHED)
        )

        assert result is job
        assert job.status == JobStatus.PUBLISHED
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_published_to_closed(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.PUBLISHED)
        service.jobs.get_job_with_company_and_skills.return_value = job

        result = asyncio.run(service.update_job_status(job.id, JobStatus.CLOSED))

        assert result is job
        assert job.status == JobStatus.CLOSED

    def test_closed_to_published_reopens(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.CLOSED)
        service.jobs.get_job_with_company_and_skills.return_value = job

        result = asyncio.run(
            service.update_job_status(job.id, JobStatus.PUBLISHED)
        )

        assert result is job
        assert job.status == JobStatus.PUBLISHED

    def test_invalid_transition_raises(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.DRAFT)
        service.jobs.get_job_with_company_and_skills.return_value = job

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.update_job_status(job.id, JobStatus.CLOSED))

        assert job.status == JobStatus.DRAFT
        session.commit.assert_not_awaited()

    def test_self_transition_raises(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.PUBLISHED)
        service.jobs.get_job_with_company_and_skills.return_value = job

        with pytest.raises(InvalidTransitionException):
            asyncio.run(
                service.update_job_status(job.id, JobStatus.PUBLISHED)
            )

    def test_expired_cannot_transition(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.EXPIRED)
        service.jobs.get_job_with_company_and_skills.return_value = job

        with pytest.raises(InvalidTransitionException):
            asyncio.run(
                service.update_job_status(job.id, JobStatus.PUBLISHED)
            )

    def test_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_job_with_company_and_skills.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.update_job_status(uuid.uuid4(), JobStatus.PUBLISHED)
            )

        session.commit.assert_not_awaited()


class TestUpdateJob:
    def test_updates_editable_fields_and_reindexes(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job(status=JobStatus.DRAFT)
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        data = JobUpdate(
            title="Senior Backend Engineer",
            description="Build scalable services",
            location="Da Nang",
            job_type=JobType.CONTRACT,
            workplace_type=WorkplaceType.HYBRID,
        )
        result = asyncio.run(service.update_job(MagicMock(), job.id, data))

        assert result is job
        assert job.title == "Senior Backend Engineer"
        assert job.description == "Build scalable services"
        assert job.location == "Da Nang"
        assert job.job_type == JobType.CONTRACT
        assert job.workplace_type == WorkplaceType.HYBRID
        embedded_text = embedding.embed_text.call_args.args[0]
        assert "Senior Backend Engineer" in embedded_text
        assert "Build scalable services" in embedded_text
        vector_repository.upsert_job_vector.assert_awaited_once_with(
            job_id=job.id,
            vector=[0.0] * 4,
            skills=[],
            created_at=job.created_at,
        )
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_ignores_status_field(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job(status=JobStatus.DRAFT)
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        data = JobUpdate(title="New Title", status=JobStatus.CLOSED)
        result = asyncio.run(service.update_job(MagicMock(), job.id, data))

        assert result is job
        assert job.status == JobStatus.DRAFT

    def test_empty_update_returns_without_commit_or_reindex(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job(status=JobStatus.DRAFT)
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        result = asyncio.run(
            service.update_job(MagicMock(), job.id, JobUpdate())
        )

        assert result is job
        session.commit.assert_not_awaited()
        embedding.embed_text.assert_not_called()
        vector_repository.upsert_job_vector.assert_not_awaited()

    def test_unowned_job_raises_not_found(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        service = make_ai_service(session, embedding, vector_repository)
        service.get_recruiter_job_by_id = AsyncMock(
            side_effect=EntityNotFoundException("Job not found")
        )

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.update_job(
                    MagicMock(), uuid.uuid4(), JobUpdate(title="New Title")
                )
            )

        session.commit.assert_not_awaited()

    def test_embedding_failure_rolls_back(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        embedding.embed_text.side_effect = RuntimeError("embedding down")
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job()
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        with pytest.raises(RuntimeError):
            asyncio.run(
                service.update_job(
                    MagicMock(), job.id, JobUpdate(title="New Title")
                )
            )

        session.rollback.assert_awaited_once()
        vector_repository.upsert_job_vector.assert_not_awaited()

    def test_vector_upsert_failure_rolls_back(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        vector_repository.upsert_job_vector.side_effect = RuntimeError(
            "qdrant down"
        )
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job()
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        with pytest.raises(RuntimeError):
            asyncio.run(
                service.update_job(
                    MagicMock(), job.id, JobUpdate(title="New Title")
                )
            )

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()


class TestDeleteJob:
    def test_soft_deletes_own_job_and_removes_vector(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job(status=JobStatus.PUBLISHED)
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        result = asyncio.run(service.delete_job(MagicMock(), job.id))

        assert result is None
        assert job.is_deleted is True
        vector_repository.delete_vector.assert_awaited_once_with(
            "jobs", job.id
        )
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_vector_delete_failure_rolls_back(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        vector_repository.delete_vector.side_effect = RuntimeError(
            "qdrant down"
        )
        service = make_ai_service(session, embedding, vector_repository)
        job = make_job()
        service.get_recruiter_job_by_id = AsyncMock(return_value=job)

        with pytest.raises(RuntimeError):
            asyncio.run(service.delete_job(MagicMock(), job.id))

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    def test_unowned_job_raises_not_found(self):
        session = make_session()
        embedding, vector_repository = make_ai_dependencies()
        service = make_ai_service(session, embedding, vector_repository)
        service.get_recruiter_job_by_id = AsyncMock(
            side_effect=EntityNotFoundException("Job not found")
        )

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.delete_job(MagicMock(), uuid.uuid4()))

        session.commit.assert_not_awaited()
        vector_repository.delete_vector.assert_not_awaited()
