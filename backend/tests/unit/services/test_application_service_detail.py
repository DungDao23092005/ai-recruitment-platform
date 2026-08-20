import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import EntityNotFoundException
from app.domain.enums import ApplicationStatus, UserRole
from app.models import Application, Job, Resume
from app.repositories import ApplicationRepository, JobRepository, ResumeRepository
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


def make_resume(
    candidate_id: uuid.UUID,
    parsed_data: dict | None = None,
) -> Resume:
    return Resume(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        title="cv.pdf",
        is_primary=True,
        parsed_data=parsed_data or {"full_name": "Jane Doe"},
    )


def make_service(session) -> ApplicationService:
    service = ApplicationService(session)
    service.applications = AsyncMock(spec=ApplicationRepository)
    service.jobs = AsyncMock(spec=JobRepository)
    return service


class TestGetApplicationDetail:
    def test_returns_application_and_resume(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        resume = make_resume(application.candidate_id)
        service.applications.get_by_id_with_candidate.return_value = application

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=job
            )
            mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock(
                return_value=resume
            )
            user = make_user()
            result_application, result_resume = asyncio.run(
                service.get_application_detail(
                    current_user=user,
                    application_id=application.id,
                )
            )

        assert result_application is application
        assert result_resume is resume
        service.applications.get_by_id_with_candidate.assert_awaited_once_with(
            application.id
        )
        mock_job_service.return_value.get_recruiter_job_by_id.assert_awaited_once_with(
            user, application.job_id
        )
        mock_resume_repo.return_value.get_primary_by_candidate.assert_awaited_once_with(
            application.candidate_id
        )

    def test_returns_none_resume_when_candidate_has_no_resume(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        service.applications.get_by_id_with_candidate.return_value = application

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=job
            )
            mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock(
                return_value=None
            )
            result_application, result_resume = asyncio.run(
                service.get_application_detail(
                    current_user=make_user(),
                    application_id=application.id,
                )
            )

        assert result_application is application
        assert result_resume is None

    def test_application_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.applications.get_by_id_with_candidate.return_value = None

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock()
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.get_application_detail(
                        current_user=make_user(),
                        application_id=uuid.uuid4(),
                    )
                )

        mock_job_service.return_value.get_recruiter_job_by_id.assert_not_awaited()

    def test_unowned_application_raises_not_found(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        service.applications.get_by_id_with_candidate.return_value = application

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                side_effect=EntityNotFoundException("Application not found")
            )
            with pytest.raises(EntityNotFoundException):
                asyncio.run(
                    service.get_application_detail(
                        current_user=make_user(),
                        application_id=application.id,
                    )
                )

            mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock()
            mock_resume_repo.return_value.get_primary_by_candidate.assert_not_awaited()
        service.applications.get_by_id_with_candidate.assert_awaited_once_with(
            application.id
        )

    def test_resume_fetched_for_owned_application(self):
        session = make_session()
        service = make_service(session)
        application = make_application()
        job = make_job()
        service.applications.get_by_id_with_candidate.return_value = application

        with patch(
            "app.services.application_service.JobService"
        ) as mock_job_service, patch(
            "app.services.application_service.ResumeRepository"
        ) as mock_resume_repo:
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=job
            )
            mock_resume_repo.return_value.get_primary_by_candidate = AsyncMock(
                return_value=None
            )
            asyncio.run(
                service.get_application_detail(
                    current_user=make_user(),
                    application_id=application.id,
                )
            )

        mock_resume_repo.return_value.get_primary_by_candidate.assert_awaited_once_with(
            application.candidate_id
        )