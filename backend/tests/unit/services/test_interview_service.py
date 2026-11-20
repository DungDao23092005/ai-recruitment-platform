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
from app.domain import hiring
from app.domain.enums import (
    ApplicationStatus,
    InterviewStatus,
    InterviewType,
    MembershipRole,
    MembershipStatus,
    UserRole,
)
from app.models import Application, CompanyMembership, Interview, Job, User
from app.repositories import ApplicationRepository, InterviewRepository
from app.schemas.interview import InterviewUpdate
from app.services.interview_service import InterviewService
from app.services.job_service import JobService
from app.services.notification_service import (
    INTERVIEW_CANCELLED_TITLE,
    INTERVIEW_CANCELLED_TYPE,
    INTERVIEW_CONFIRMED_TITLE,
    INTERVIEW_CONFIRMED_TYPE,
    INTERVIEW_DECLINED_TITLE,
    INTERVIEW_DECLINED_TYPE,
    INTERVIEW_UPDATED_TITLE,
    INTERVIEW_UPDATED_TYPE,
    NotificationService,
    candidate_interview_response_notification_id,
    interview_schedule_notification_id,
)
from app.services.user_service import UserService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    return session


def capture_add_and_materialize_uuid(session: MagicMock, call_order: list = None):
    """
    Capture objects added to session and materialize UUID on flush.

    This simulates SQLAlchemy behavior where:
    1. Object is created with id=None (or callable default)
    2. session.add(obj) adds to session
    3. session.flush() materializes the UUID (calls default=uuid.uuid4)
    4. After flush, obj.id is populated
    """
    captured_objects = []

    original_add = session.add

    def capture_add(obj):
        captured_objects.append(obj)
        original_add(obj)

    session.add = capture_add

    async def mock_flush():
        if call_order is not None:
            call_order.append("flush")
        for obj in captured_objects:
            if hasattr(obj, 'id') and obj.id is None:
                obj.id = uuid.uuid4()

    session.flush = mock_flush

    return captured_objects


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

    @pytest.fixture(autouse=True)
    def _patch_pipeline_side_effects(self, monkeypatch):
        async def _noop(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.services.interview_service.record_activity", _noop
        )
        monkeypatch.setattr(
            "app.services.interview_service.schedule_interview_email", _noop
        )

    @pytest.mark.asyncio
    async def test_flush_called_before_notification(self):
        """Verify flush is called before notification uses interview.id."""
        session = make_session()

        # Track call order
        call_order = []

        # Capture objects and materialize UUID on flush
        captured_objects = capture_add_and_materialize_uuid(session, call_order)

        async def mock_commit():
            call_order.append("commit")

        async def mock_refresh(obj):
            call_order.append("refresh")

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
            status=ApplicationStatus.APPLIED,
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
        """Verify notification is created with entity_id == interview.id after flush materializes UUID."""
        session = make_session()

        # Capture objects and materialize UUID on flush
        captured_objects = capture_add_and_materialize_uuid(session)

        # Create mock application with candidate and job
        mock_candidate = MagicMock(user_id=uuid.uuid4())
        mock_job = MagicMock(title="Test Job")
        mock_application = MagicMock(
            candidate=mock_candidate,
            job=mock_job,
            id=uuid.uuid4(),
            candidate_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            status=ApplicationStatus.APPLIED,
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

        # Check that entity_id is passed
        assert "entity_id" in call_kwargs, "entity_id not passed to create_notification"

        # Get the interview that was created (first non-Application object added)
        interview_obj = None
        for obj in captured_objects:
            if hasattr(obj, 'id') and not isinstance(obj, Application):
                interview_obj = obj
                break

        assert interview_obj is not None, "Interview was not created"

        # CRITICAL: Verify UUID was materialized by flush
        interview_id = interview_obj.id
        assert interview_id is not None, "interview.id should be materialized after flush, but is None"
        assert isinstance(interview_id, uuid.UUID), f"interview.id should be UUID, got {type(interview_id)}"

        notification_entity_id = call_kwargs["entity_id"]

        assert notification_entity_id == interview_id, \
            f"entity_id ({notification_entity_id}) does not match interview.id ({interview_id})"


class TestInterviewLifecycleNotifications:
    @pytest.mark.asyncio
    async def test_update_interview_notifies_candidate_and_assigned_interviewers(self, monkeypatch):
        session = make_session()
        service = InterviewService(session)

        interview_id = uuid.uuid4()
        application_id = uuid.uuid4()
        candidate_user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        interviewer_user_id = uuid.uuid4()

        now = datetime.now(timezone.utc)
        original_time = now + timedelta(days=2)
        new_time = now + timedelta(days=3)

        interview = MagicMock(
            id=interview_id,
            application_id=application_id,
            scheduled_at=original_time,
            duration_minutes=60,
            interview_type=InterviewType.TECHNICAL,
            meeting_url="https://meet.old.com",
            location="Room 1",
            notes="Notes",
            status=InterviewStatus.SCHEDULED,
        )

        application = MagicMock(
            id=application_id,
            job_id=uuid.uuid4(),
            candidate_id=uuid.uuid4(),
            job=MagicMock(company_id=company_id, title="Lead Dev"),
            candidate=MagicMock(user_id=candidate_user_id, user=MagicMock(email="cand@test.com")),
        )

        service.interviews.get_by_id_with_application = AsyncMock(return_value=interview)
        service.applications.get_by_id_with_candidate_job_company_and_recruiters = AsyncMock(return_value=application)

        interviewer_user = User(id=interviewer_user_id, email="interviewer@corp.com", is_active=True)
        service.assignments.list_active_by_interview = AsyncMock(return_value=[MagicMock(user_id=interviewer_user_id)])
        service.users.get_by_id = AsyncMock(return_value=interviewer_user)

        activity_record = MagicMock(id=uuid.uuid4())
        record_activity_mock = AsyncMock(return_value=activity_record)
        monkeypatch.setattr("app.services.interview_service.record_activity", record_activity_mock)

        emails_scheduled = []
        async def _mock_schedule_interview_email(*args, **kwargs):
            emails_scheduled.append(kwargs)
        async def _mock_schedule_interviewer_email(*args, **kwargs):
            emails_scheduled.append(kwargs)

        monkeypatch.setattr("app.services.interview_service.schedule_interview_email", _mock_schedule_interview_email)
        monkeypatch.setattr("app.services.interview_service.schedule_interviewer_schedule_change_email", _mock_schedule_interviewer_email)

        notifications_created = []
        class FakeNotificationService:
            def __init__(self, s):
                self.session = s
                self.notifications = MagicMock()
                self.notifications.get_by_id_and_user = AsyncMock(return_value=None)
            async def create_notification(self, **kwargs):
                notifications_created.append(kwargs)
                return MagicMock()

        monkeypatch.setattr("app.services.interview_service.NotificationService", FakeNotificationService)
        monkeypatch.setattr("app.services.interview_service.JobService.get_recruiter_job_by_id", AsyncMock())
        monkeypatch.setattr("app.services.interview_service.InterviewRead.model_validate", lambda v: v)
        monkeypatch.setattr("app.services.interview_service.schedule_application_pipeline_event", AsyncMock())

        update_data = InterviewUpdate(
            scheduled_at=new_time,
            meeting_url="https://meet.new.com",
        )

        await service.update_interview(
            current_user=make_user(),
            interview_id=interview_id,
            data=update_data,
        )

        # 1. Activity recorded
        record_activity_mock.assert_awaited_once()

        # 2. In-App notifications: 1 to candidate, 1 to active interviewer
        assert len(notifications_created) == 2
        cand_notif = next(n for n in notifications_created if n["user_id"] == candidate_user_id)
        assert cand_notif["notification_type"] == INTERVIEW_UPDATED_TYPE
        assert cand_notif["notification_id"] == interview_schedule_notification_id("updated", candidate_user_id, activity_record.id)

        int_notif = next(n for n in notifications_created if n["user_id"] == interviewer_user_id)
        assert int_notif["notification_type"] == INTERVIEW_UPDATED_TYPE
        assert int_notif["notification_id"] == interview_schedule_notification_id("rescheduled", interviewer_user_id, activity_record.id)

        # 3. Emails: 1 to candidate, 1 to active interviewer
        assert len(emails_scheduled) == 2
        cand_email = next(e for e in emails_scheduled if e["to_email"] == "cand@test.com")
        assert str(activity_record.id) in cand_email["idempotency_key"]

        int_email = next(e for e in emails_scheduled if e["to_email"] == "interviewer@corp.com")
        assert str(activity_record.id) in int_email["idempotency_key"]

    @pytest.mark.asyncio
    async def test_candidate_confirm_notifies_admins_recruiters_in_app_only_no_email_option_a(self, monkeypatch):
        session = make_session()
        service = InterviewService(session)

        interview_id = uuid.uuid4()
        application_id = uuid.uuid4()
        candidate_user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        recruiter_id = uuid.uuid4()

        interview = MagicMock(
            id=interview_id,
            application_id=application_id,
            status=InterviewStatus.SCHEDULED,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
        )

        application = MagicMock(
            id=application_id,
            candidate_id=uuid.uuid4(),
            job=MagicMock(company_id=company_id, title="DevOps Engineer"),
            candidate=MagicMock(id=uuid.uuid4(), user_id=candidate_user_id, full_name="Candidate A"),
        )

        user_with_profile = MagicMock(candidate_profile=MagicMock(id=application.candidate_id))
        monkeypatch.setattr("app.services.interview_service.UserService.get_user_with_profile", AsyncMock(return_value=user_with_profile))

        service.applications.get_by_id_with_candidate_job_company_and_recruiters = AsyncMock(return_value=application)
        service.interviews.get_by_id_with_application = AsyncMock(return_value=interview)

        recruiter_user = User(id=recruiter_id, email="recruiter@corp.com", is_active=True)
        service._get_active_company_recruitment_recipients = AsyncMock(return_value=[recruiter_user])

        activity_record = MagicMock(id=uuid.uuid4())
        record_activity_mock = AsyncMock(return_value=activity_record)
        monkeypatch.setattr("app.services.interview_service.record_activity", record_activity_mock)

        emails_scheduled = []
        async def _mock_schedule_email(*args, **kwargs):
            emails_scheduled.append(kwargs)
        monkeypatch.setattr("app.services.interview_service.schedule_interview_declined_recruiter_email", _mock_schedule_email)

        notifications_created = []
        class FakeNotificationService:
            def __init__(self, s):
                self.session = s
                self.notifications = MagicMock()
                self.notifications.get_by_id_and_user = AsyncMock(return_value=None)
            async def create_notification(self, **kwargs):
                notifications_created.append(kwargs)
                return MagicMock()

        monkeypatch.setattr("app.services.interview_service.NotificationService", FakeNotificationService)
        monkeypatch.setattr("app.services.interview_service.CandidateInterviewRead.model_validate", lambda v: v)
        monkeypatch.setattr("app.services.interview_service.schedule_application_pipeline_event", AsyncMock())

        await service.candidate_action_interview(
            current_user=SimpleNamespace(id=candidate_user_id),
            application_id=application_id,
            interview_id=interview_id,
            action="confirm",
        )

        # In-App notification sent to active recruiter/admin
        assert len(notifications_created) == 1
        assert notifications_created[0]["user_id"] == recruiter_id
        assert notifications_created[0]["notification_type"] == INTERVIEW_CONFIRMED_TYPE
        assert notifications_created[0]["title"] == INTERVIEW_CONFIRMED_TITLE

        # Option A: NO email to recruiter on confirm, NO notification to interviewers
        assert len(emails_scheduled) == 0

    @pytest.mark.asyncio
    async def test_candidate_decline_notifies_admins_recruiters_in_app_and_email_option_a(self, monkeypatch):
        session = make_session()
        service = InterviewService(session)

        interview_id = uuid.uuid4()
        application_id = uuid.uuid4()
        candidate_user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        recruiter_id = uuid.uuid4()

        interview = MagicMock(
            id=interview_id,
            application_id=application_id,
            status=InterviewStatus.SCHEDULED,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
            candidate_notes="Cannot attend",
        )

        application = MagicMock(
            id=application_id,
            candidate_id=uuid.uuid4(),
            job=MagicMock(company_id=company_id, title="DevOps Engineer"),
            candidate=MagicMock(id=uuid.uuid4(), user_id=candidate_user_id, full_name="Candidate A"),
        )

        user_with_profile = MagicMock(candidate_profile=MagicMock(id=application.candidate_id))
        monkeypatch.setattr("app.services.interview_service.UserService.get_user_with_profile", AsyncMock(return_value=user_with_profile))

        service.applications.get_by_id_with_candidate_job_company_and_recruiters = AsyncMock(return_value=application)
        service.interviews.get_by_id_with_application = AsyncMock(return_value=interview)
        service._reconcile_application_interview_stage = AsyncMock(return_value=False)

        recruiter_user = User(id=recruiter_id, email="recruiter@corp.com", is_active=True)
        service._get_active_company_recruitment_recipients = AsyncMock(return_value=[recruiter_user])

        activity_record = MagicMock(id=uuid.uuid4())
        record_activity_mock = AsyncMock(return_value=activity_record)
        monkeypatch.setattr("app.services.interview_service.record_activity", record_activity_mock)

        emails_scheduled = []
        async def _mock_schedule_email(*args, **kwargs):
            emails_scheduled.append(kwargs)
        monkeypatch.setattr("app.services.interview_service.schedule_interview_declined_recruiter_email", _mock_schedule_email)

        notifications_created = []
        class FakeNotificationService:
            def __init__(self, s):
                self.session = s
                self.notifications = MagicMock()
                self.notifications.get_by_id_and_user = AsyncMock(return_value=None)
            async def create_notification(self, **kwargs):
                notifications_created.append(kwargs)
                return MagicMock()

        monkeypatch.setattr("app.services.interview_service.NotificationService", FakeNotificationService)
        monkeypatch.setattr("app.services.interview_service.CandidateInterviewRead.model_validate", lambda v: v)
        monkeypatch.setattr("app.services.interview_service.schedule_application_pipeline_event", AsyncMock())

        await service.candidate_action_interview(
            current_user=SimpleNamespace(id=candidate_user_id),
            application_id=application_id,
            interview_id=interview_id,
            action="decline",
            candidate_notes="Cannot attend",
        )

        # 1. In-App notification sent to active recruiter/admin
        assert len(notifications_created) == 1
        assert notifications_created[0]["user_id"] == recruiter_id
        assert notifications_created[0]["notification_type"] == INTERVIEW_DECLINED_TYPE
        assert notifications_created[0]["title"] == INTERVIEW_DECLINED_TITLE

        # 2. On decline, transactional Email Outbox is scheduled for recruiter
        assert len(emails_scheduled) == 1
        assert emails_scheduled[0]["to_email"] == "recruiter@corp.com"
        assert emails_scheduled[0]["job_title"] == "DevOps Engineer"
        assert f"interview-declined:{interview_id}:{recruiter_id}:{activity_record.id}" == emails_scheduled[0]["idempotency_key"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
