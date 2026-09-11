from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    EntityNotFoundException,
    InvalidTransitionException,
)
from app.domain.enums import ApplicationStatus, InterviewStatus, InterviewType, UserRole
from app.models import Application, Interview, Job
from app.repositories import ApplicationRepository, InterviewRepository
from app.services.interview_service import InterviewService
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    return session


def make_user(role: UserRole = UserRole.RECRUITER):
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
    job = Job(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        description="Build APIs",
        status="published",
        job_type="full_time",
        workplace_type="remote",
        location="",
    )
    job.company = MagicMock()
    job.company.name = "Test Company"
    job.company.recruiters = [MagicMock(user_id=uuid.uuid4())]
    return job


class TestScheduleInterviewFlush:
    """Test that flush() is called before using interview.id for notifications."""

    @pytest.mark.asyncio
    async def test_flush_called_before_notification(self):
        """Verify flush is called before notification uses interview.id."""
        session = make_session()

        # Track call order
        call_order = []

        async def mock_flush():
            call_order.append("flush")

        async def mock_commit():
            call_order.append("commit")

        async def mock_refresh(obj):
            call_order.append("refresh")

        session.flush = mock_flush
        session.commit = mock_commit
        session.refresh = AsyncMock()

        # Create mock application with candidate and job
        mock_candidate = MagicMock(user_id=uuid.uuid4())
        mock_job = MagicMock(title="Test Job")
        mock_application = MagicMock(
            candidate=mock_candidate,
            job=mock_job,
            id=uuid.uuid4(),
            candidate_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            status="applied",
        )

        # Mock NotificationService.create_notification to track when it's called
        notification_calls = []

        async def mock_create_notification(**kwargs):
            call_order.append("notification")
            notification_calls.append(kwargs)

        # Patch NotificationService at the module where it's used (interview_service)
        with patch(
            "app.services.interview_service.InterviewRead.model_validate"
        ) as mock_validate, patch(
            "app.services.interview_service.JobService"
        ) as mock_job_service, patch(
            "app.services.interview_service.NotificationService"
        ) as mock_notification_service_class:
            mock_validate.return_value = MagicMock()
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=MagicMock()
            )
            mock_notification_service_class.return_value.create_notification = mock_create_notification

            service = InterviewService(session)
            service.applications = AsyncMock()
            service.applications.get_by_id_with_candidate_job_company_and_recruiters = AsyncMock(
                return_value=mock_application
            )

            data = MagicMock(
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                duration_minutes=60,
                interview_type="technical",
                meeting_url="https://meet.example.com",
                location="Office",
                notes="Test interview",
            )

            await service.schedule_interview(
                current_user=MagicMock(id=uuid.uuid4(), role="recruiter"),
                application_id=uuid.uuid4(),
                data=data,
            )

        # Verify flush was called
        assert "flush" in call_order, "flush() was not called"
        # Verify notification was called
        assert "notification" in call_order, "notification was not called"
        # Verify commit was called
        assert "commit" in call_order, "commit() was not called"
        
        # Verify order: flush -> notification -> commit
        flush_index = call_order.index("flush")
        notification_index = call_order.index("notification")
        commit_index = call_order.index("commit")
        
        assert flush_index < notification_index, "flush() must be called before notification"
        assert notification_index < commit_index, "notification must be called before commit()"

    @pytest.mark.asyncio
    async def test_notification_entity_id_equals_interview_id(self):
        """Verify notification is created with entity_id == interview.id."""
        session = make_session()
        
        # Capture the interview that gets added to session
        captured_interview = []
        
        original_add = session.add
        def capture_add(obj):
            captured_interview.append(obj)
            original_add(obj)
        session.add = capture_add

        # Create mock application with candidate and job
        mock_candidate = MagicMock(user_id=uuid.uuid4())
        mock_job = MagicMock(title="Test Job")
        mock_application = MagicMock(
            candidate=mock_candidate,
            job=mock_job,
            id=uuid.uuid4(),
            candidate_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            status="applied",
        )

        # Track notification calls with arguments
        notification_calls = []

        async def mock_create_notification(**kwargs):
            notification_calls.append(kwargs)

        # Patch NotificationService at the module where it's used (interview_service)
        with patch(
            "app.services.interview_service.InterviewRead.model_validate"
        ) as mock_validate, patch(
            "app.services.interview_service.JobService"
        ) as mock_job_service, patch(
            "app.services.interview_service.NotificationService"
        ) as mock_notification_service_class:
            mock_validate.return_value = MagicMock()
            mock_job_service.return_value.get_recruiter_job_by_id = AsyncMock(
                return_value=MagicMock()
            )
            mock_notification_service_class.return_value.create_notification = mock_create_notification

            service = InterviewService(session)
            service.applications = AsyncMock()
            service.applications.get_by_id_with_candidate_job_company_and_recruiters = AsyncMock(
                return_value=mock_application
            )

            data = MagicMock(
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                duration_minutes=60,
                interview_type="technical",
                meeting_url="https://meet.example.com",
                location="Office",
                notes="Test interview",
            )

            await service.schedule_interview(
                current_user=MagicMock(id=uuid.uuid4(), role="recruiter"),
                application_id=uuid.uuid4(),
                data=data,
            )

        # Verify notification was created
        assert len(notification_calls) == 1, "create_notification was not called exactly once"
        call_kwargs = notification_calls[0]
        
        # Check that entity_id matches the interview.id
        assert "entity_id" in call_kwargs, "entity_id not passed to create_notification"
        
        # Get the interview that was created (first non-Application object added)
        interview_obj = None
        for obj in captured_interview:
            if hasattr(obj, 'id') and not isinstance(obj, Application):
                interview_obj = obj
                break
        
        assert interview_obj is not None, "Interview was not created"
        interview_id = interview_obj.id
        notification_entity_id = call_kwargs["entity_id"]
        
        assert notification_entity_id == interview_id, \
            f"entity_id ({notification_entity_id}) does not match interview.id ({interview_id})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])