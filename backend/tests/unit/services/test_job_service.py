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
from app.schemas.job import JobCreate
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
        service.jobs.get_by_id.return_value = job

        result = asyncio.run(service.publish_job(job.id))

        assert result is job
        assert job.status == JobStatus.PUBLISHED
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_job_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.publish_job(uuid.uuid4()))

        session.commit.assert_not_awaited()

    def test_non_draft_raises_invalid_transition(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.PUBLISHED)
        service.jobs.get_by_id.return_value = job

        with pytest.raises(InvalidTransitionException):
            asyncio.run(service.publish_job(job.id))

        session.commit.assert_not_awaited()


class TestCloseJob:
    def test_closes_published(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.PUBLISHED)
        service.jobs.get_by_id.return_value = job

        result = asyncio.run(service.close_job(job.id))

        assert result is job
        assert job.status == JobStatus.CLOSED
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    def test_job_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.close_job(uuid.uuid4()))

        session.commit.assert_not_awaited()

    def test_non_published_raises_invalid_transition(self):
        session = make_session()
        service = make_service(session)
        job = make_job(status=JobStatus.DRAFT)
        service.jobs.get_by_id.return_value = job

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
