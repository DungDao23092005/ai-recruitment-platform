import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import ApplicationStatus, UserRole
from app.models import Application, Job
from app.repositories import ApplicationRepository, JobRepository
from app.services.application_service import ApplicationService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_user(
    role: UserRole = UserRole.RECRUITER,
) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role, is_active=True)


def make_application(
    application_id: uuid.UUID | None = None,
    status: ApplicationStatus = ApplicationStatus.APPLIED,
) -> Application:
    return Application(
        id=application_id or uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        status=status,
    )


def make_job() -> Job:
    return Job(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        description="Build APIs",
        status="published",
        job_type="full_time",
        workplace_type="remote",
        location="",
    )


def make_service(session) -> ApplicationService:
    service = ApplicationService(session)
    service.applications = AsyncMock(spec=ApplicationRepository)
    service.jobs = AsyncMock(spec=JobRepository)
    return service


class TestApplyJob:
    def test_creates_application(self):
        session = make_session()
        service = make_service(session)
        job = make_job()
        service.jobs.get_by_id.return_value = job
        service.applications.get_by_candidate_and_job.return_value = None
        candidate_id = uuid.uuid4()

        application = asyncio.run(
            service.apply_job(candidate_id=candidate_id, job_id=job.id)
        )

        assert application.candidate_id == candidate_id
        assert application.job_id == job.id
        session.add.assert_called_once_with(application)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(
            application, attribute_names=["candidate"]
        )

    def test_job_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_by_id.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.apply_job(
                    candidate_id=uuid.uuid4(),
                    job_id=uuid.uuid4(),
                )
            )

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_duplicate_application_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_by_id.return_value = make_job()
        service.applications.get_by_candidate_and_job.return_value = (
            make_application()
        )

        with pytest.raises(ConflictException):
            asyncio.run(
                service.apply_job(
                    candidate_id=uuid.uuid4(),
                    job_id=uuid.uuid4(),
                )
            )

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        service.jobs.get_by_id.return_value = make_job()
        service.applications.get_by_candidate_and_job.return_value = None
        session.commit.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError):
            asyncio.run(
                service.apply_job(
                    candidate_id=uuid.uuid4(),
                    job_id=uuid.uuid4(),
                )
            )

        session.rollback.assert_awaited_once()


class TestListApplicationsByJob:
    def test_returns_applications_for_job(self):
        session = make_session()
        service = make_service(session)
        job_id = uuid.uuid4()
        expected = [make_application(), make_application()]
        service.applications.list_by_job.return_value = expected

        result = asyncio.run(service.list_applications_by_job(job_id))

        service.applications.list_by_job.assert_awaited_once_with(job_id)
        assert result == expected

    def test_returns_empty_list_when_no_applications(self):
        session = make_session()
        service = make_service(session)
        service.applications.list_by_job.return_value = []

        result = asyncio.run(
            service.list_applications_by_job(uuid.uuid4())
        )

        assert result == []

    def test_passes_correct_job_id_to_repository(self):
        session = make_session()
        service = make_service(session)
        job_id = uuid.uuid4()
        service.applications.list_by_job.return_value = []

        asyncio.run(service.list_applications_by_job(job_id))

        service.applications.list_by_job.assert_awaited_once_with(job_id)


class TestUpdateApplicationStatus:
    def test_valid_transition(self):
        session = make_session()
        service = make_service(session)
        application = make_application(status=ApplicationStatus.APPLIED)
        service.applications.get_by_id.return_value = application
        job = make_job()

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=job
            )
            result = asyncio.run(
                service.update_application_status(
                    current_user=make_user(),
                    application_id=application.id,
                    new_status=ApplicationStatus.UNDER_REVIEW,
                )
            )

        assert result is application
        assert application.status == ApplicationStatus.UNDER_REVIEW
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(
            application, attribute_names=["candidate"]
        )

    def test_application_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.applications.get_by_id.return_value = None

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.update_application_status(
                        current_user=make_user(),
                        application_id=uuid.uuid4(),
                        new_status=ApplicationStatus.UNDER_REVIEW,
                    )
                )

        mock_job_service.return_value.get_recruiter_job_by_id.assert_not_called()
        session.commit.assert_not_awaited()

    def test_unowned_application_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        application = make_application(status=ApplicationStatus.APPLIED)
        service.applications.get_by_id.return_value = application

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                side_effect=EntityNotFoundException("Application not found")
            )
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.update_application_status(
                        current_user=make_user(),
                        application_id=application.id,
                        new_status=ApplicationStatus.UNDER_REVIEW,
                    )
                )

        assert application.status == ApplicationStatus.APPLIED
        session.commit.assert_not_awaited()

    def test_invalid_transition_raises(self):
        session = make_session()
        service = make_service(session)
        application = make_application(status=ApplicationStatus.APPLIED)
        service.applications.get_by_id.return_value = application

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=make_job()
            )
            with pytest.raises(InvalidTransitionException):
                asyncio.run(
                    service.update_application_status(
                        current_user=make_user(),
                        application_id=application.id,
                        new_status=ApplicationStatus.ACCEPTED,
                    )
                )

        session.commit.assert_not_awaited()
        assert application.status == ApplicationStatus.APPLIED

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        application = make_application(status=ApplicationStatus.APPLIED)
        service.applications.get_by_id.return_value = application
        session.commit.side_effect = RuntimeError("db down")

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=make_job()
            )
            with pytest.raises(RuntimeError):
                asyncio.run(
                    service.update_application_status(
                        current_user=make_user(),
                        application_id=application.id,
                        new_status=ApplicationStatus.UNDER_REVIEW,
                    )
                )

        session.rollback.assert_awaited_once()
