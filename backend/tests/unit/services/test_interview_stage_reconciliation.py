"""Application stage reconciliation after interview decline/cancellation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import InvalidTransitionException
from app.domain import hiring
from app.domain.enums import ApplicationStatus, InterviewStatus
from app.services.interview_service import InterviewService
from app.services.pipeline_realtime import (
    ACTION_INTERVIEW_CANCELLED,
    ACTION_INTERVIEW_CONFIRMED,
    ACTION_INTERVIEW_DECLINED,
    ACTION_INTERVIEW_UPDATED,
)

MODULE = "app.services.interview_service"


def make_session() -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


def make_application(
    status: ApplicationStatus = ApplicationStatus.INTERVIEWING,
) -> SimpleNamespace:
    candidate_user_id = uuid.uuid4()
    job = SimpleNamespace(
        id=uuid.uuid4(),
        title="Backend Engineer",
        company=SimpleNamespace(
            recruiters=[SimpleNamespace(user_id=uuid.uuid4())]
        ),
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        job_id=job.id,
        status=status,
        candidate=SimpleNamespace(
            id=uuid.uuid4(),
            user_id=candidate_user_id,
            user=SimpleNamespace(
                id=candidate_user_id, email="candidate@example.com"
            ),
        ),
        job=job,
    )


def make_interview(
    application: SimpleNamespace,
    status: InterviewStatus = InterviewStatus.SCHEDULED,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        application_id=application.id,
        scheduled_at=now + timedelta(days=2),
        duration_minutes=60,
        interview_type="technical",
        meeting_url=None,
        location="Room 1",
        notes=None,
        candidate_notes=None,
        status=status,
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )


def make_update_data(**overrides) -> SimpleNamespace:
    values = {
        "scheduled_at": None,
        "duration_minutes": None,
        "interview_type": None,
        "meeting_url": None,
        "location": None,
        "notes": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def side_effects(monkeypatch):
    activities: list[dict] = []
    events: list[dict] = []
    notifications: list[dict] = []
    emails: list[dict] = []

    async def record_activity(session, **kwargs):
        activities.append(kwargs)
        return MagicMock()

    async def schedule_event(session, **kwargs):
        events.append(kwargs)

    async def schedule_email(session, **kwargs):
        emails.append(kwargs)
        return MagicMock()

    class FakeNotificationService:
        def __init__(self, session):
            pass

        async def create_notification(self, **kwargs):
            notifications.append(kwargs)
            return MagicMock()

    monkeypatch.setattr(f"{MODULE}.record_activity", record_activity)
    monkeypatch.setattr(
        f"{MODULE}.schedule_application_pipeline_event", schedule_event
    )
    monkeypatch.setattr(f"{MODULE}.schedule_interview_email", schedule_email)
    monkeypatch.setattr(
        f"{MODULE}.NotificationService", FakeNotificationService
    )
    monkeypatch.setattr(
        f"{MODULE}.CandidateInterviewRead.model_validate",
        lambda value: value,
    )
    monkeypatch.setattr(
        f"{MODULE}.InterviewRead.model_validate", lambda value: value
    )

    return SimpleNamespace(
        activities=activities,
        events=events,
        notifications=notifications,
        emails=emails,
    )


def build_service(application, interview, *, remaining, reconciled=True):
    session = make_session()
    service = InterviewService(session)
    service.applications = AsyncMock()
    service.applications.get_by_id_with_candidate_job_company_and_recruiters = (
        AsyncMock(return_value=application)
    )
    service.applications.try_update_status = AsyncMock(return_value=reconciled)
    service.interviews = AsyncMock()
    service.interviews.get_by_id_with_application = AsyncMock(
        return_value=interview
    )
    service.interviews.list_by_application = AsyncMock(
        return_value=remaining
    )
    service.interviews.soft_delete = AsyncMock()
    return service, session


def patch_candidate_profile(monkeypatch, application):
    user_service = SimpleNamespace(
        get_user_with_profile=AsyncMock(
            return_value=SimpleNamespace(
                candidate_profile=SimpleNamespace(id=application.candidate_id)
            )
        )
    )
    monkeypatch.setattr(
        f"{MODULE}.UserService", lambda session: user_service
    )


def patch_recruiter_job(monkeypatch):
    job_service = SimpleNamespace(
        get_recruiter_job_by_id=AsyncMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        f"{MODULE}.JobService", lambda session: job_service
    )


class TestCandidateDeclineReconciliation:
    @pytest.mark.asyncio
    async def test_declining_only_interview_returns_application_to_review(
        self, side_effects, monkeypatch
    ):
        application = make_application()
        interview = make_interview(application)
        patch_candidate_profile(monkeypatch, application)
        service, session = build_service(
            application, interview, remaining=[interview]
        )
        candidate = SimpleNamespace(id=application.candidate.user_id)

        result = await service.candidate_action_interview(
            current_user=candidate,
            application_id=application.id,
            interview_id=interview.id,
            action="decline",
            candidate_notes="  Không thể tham dự  ",
        )

        assert result.status == InterviewStatus.CANDIDATE_DECLINED
        assert interview.status == InterviewStatus.CANDIDATE_DECLINED
        assert interview.candidate_notes == "Không thể tham dự"
        assert application.status == ApplicationStatus.UNDER_REVIEW
        service.applications.try_update_status.assert_awaited_once_with(
            application_id=application.id,
            expected_status=ApplicationStatus.INTERVIEWING,
            new_status=ApplicationStatus.UNDER_REVIEW,
        )
        assert session.rollback.await_count == 0

        actions = [row["action_type"] for row in side_effects.activities]
        assert actions == [hiring.INTERVIEW_DECLINED, hiring.STATUS_CHANGED]
        decline, stage = side_effects.activities
        assert decline["metadata"] == {
            "interview_id": str(interview.id),
            "candidate_notes": "Không thể tham dự",
        }
        assert stage["actor_id"] == candidate.id
        assert stage["from_status"] == "interviewing"
        assert stage["to_status"] == "under_review"
        assert stage["note"]

        assert len(side_effects.events) == 1
        event = side_effects.events[0]
        assert event["action"] == ACTION_INTERVIEW_DECLINED
        assert event["from_status"] == ApplicationStatus.INTERVIEWING
        assert event["to_status"] == ApplicationStatus.UNDER_REVIEW
        assert event["candidate_user_id"] == candidate.id

        assert len(side_effects.notifications) == 1
        assert "Đang xem xét" in side_effects.notifications[0]["content"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "active_status",
        [
            InterviewStatus.SCHEDULED,
            InterviewStatus.CANDIDATE_CONFIRMED,
            InterviewStatus.COMPLETED,
        ],
    )
    async def test_another_active_interview_keeps_application_interviewing(
        self, active_status, side_effects, monkeypatch
    ):
        application = make_application()
        interview = make_interview(application)
        other = SimpleNamespace(status=active_status)
        patch_candidate_profile(monkeypatch, application)
        service, _ = build_service(
            application, interview, remaining=[interview, other]
        )

        await service.candidate_action_interview(
            current_user=SimpleNamespace(id=application.candidate.user_id),
            application_id=application.id,
            interview_id=interview.id,
            action="decline",
            candidate_notes="Unavailable",
        )

        assert interview.status == InterviewStatus.CANDIDATE_DECLINED
        assert application.status == ApplicationStatus.INTERVIEWING
        service.applications.try_update_status.assert_not_awaited()
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_DECLINED]
        assert side_effects.events[0]["to_status"] == (
            ApplicationStatus.INTERVIEWING
        )

    @pytest.mark.asyncio
    async def test_non_interviewing_application_is_not_rewritten(
        self, side_effects, monkeypatch
    ):
        application = make_application(ApplicationStatus.OFFERED)
        interview = make_interview(application)
        patch_candidate_profile(monkeypatch, application)
        service, _ = build_service(
            application, interview, remaining=[interview]
        )

        await service.candidate_action_interview(
            current_user=SimpleNamespace(id=application.candidate.user_id),
            application_id=application.id,
            interview_id=interview.id,
            action="decline",
            candidate_notes="Changed my mind",
        )

        assert application.status == ApplicationStatus.OFFERED
        service.applications.try_update_status.assert_not_awaited()
        service.interviews.list_by_application.assert_not_awaited()
        assert side_effects.events[0]["from_status"] == (
            ApplicationStatus.OFFERED
        )
        assert side_effects.events[0]["to_status"] == (
            ApplicationStatus.OFFERED
        )

    @pytest.mark.asyncio
    async def test_concurrent_stage_change_is_not_overwritten(
        self, side_effects, monkeypatch
    ):
        application = make_application()
        interview = make_interview(application)
        patch_candidate_profile(monkeypatch, application)
        service, session = build_service(
            application,
            interview,
            remaining=[interview],
            reconciled=False,
        )

        async def refresh(entity, attribute_names=None):
            if entity is application:
                application.status = ApplicationStatus.OFFERED

        session.refresh = AsyncMock(side_effect=refresh)

        await service.candidate_action_interview(
            current_user=SimpleNamespace(id=application.candidate.user_id),
            application_id=application.id,
            interview_id=interview.id,
            action="decline",
            candidate_notes="No longer available",
        )

        assert application.status == ApplicationStatus.OFFERED
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_DECLINED]
        assert side_effects.events[0]["to_status"] == (
            ApplicationStatus.OFFERED
        )

    @pytest.mark.asyncio
    async def test_confirm_does_not_reconcile(
        self, side_effects, monkeypatch
    ):
        application = make_application()
        interview = make_interview(application)
        patch_candidate_profile(monkeypatch, application)
        service, _ = build_service(
            application, interview, remaining=[interview]
        )

        await service.candidate_action_interview(
            current_user=SimpleNamespace(id=application.candidate.user_id),
            application_id=application.id,
            interview_id=interview.id,
            action="confirm",
        )

        assert interview.status == InterviewStatus.CANDIDATE_CONFIRMED
        assert application.status == ApplicationStatus.INTERVIEWING
        service.applications.try_update_status.assert_not_awaited()
        service.interviews.list_by_application.assert_not_awaited()
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_CONFIRMED]
        assert side_effects.events[0]["action"] == (
            ACTION_INTERVIEW_CONFIRMED
        )

    @pytest.mark.asyncio
    async def test_decline_still_requires_notes(self, monkeypatch):
        application = make_application()
        interview = make_interview(application)
        patch_candidate_profile(monkeypatch, application)
        service, _ = build_service(
            application, interview, remaining=[interview]
        )

        with pytest.raises(InvalidTransitionException):
            await service.candidate_action_interview(
                current_user=SimpleNamespace(
                    id=application.candidate.user_id
                ),
                application_id=application.id,
                interview_id=interview.id,
                action="decline",
                candidate_notes="   ",
            )

        assert interview.status == InterviewStatus.SCHEDULED


class TestRecruiterCancellationReconciliation:
    @pytest.mark.asyncio
    async def test_cancelling_only_interview_returns_application_to_review(
        self, side_effects, monkeypatch
    ):
        application = make_application()
        interview = make_interview(application)
        patch_recruiter_job(monkeypatch)
        service, session = build_service(
            application, interview, remaining=[interview]
        )
        recruiter = SimpleNamespace(id=uuid.uuid4(), role="recruiter")

        result = await service.cancel_interview(
            current_user=recruiter,
            interview_id=interview.id,
        )

        assert result.status == InterviewStatus.CANCELLED
        assert interview.status == InterviewStatus.CANCELLED
        service.interviews.soft_delete.assert_awaited_once_with(interview)
        assert application.status == ApplicationStatus.UNDER_REVIEW
        service.applications.try_update_status.assert_awaited_once_with(
            application_id=application.id,
            expected_status=ApplicationStatus.INTERVIEWING,
            new_status=ApplicationStatus.UNDER_REVIEW,
        )
        assert session.rollback.await_count == 0

        actions = [row["action_type"] for row in side_effects.activities]
        assert actions == [hiring.INTERVIEW_CANCELLED, hiring.STATUS_CHANGED]
        stage = side_effects.activities[1]
        assert stage["actor_id"] == recruiter.id
        assert stage["from_status"] == "interviewing"
        assert stage["to_status"] == "under_review"
        assert "hủy phỏng vấn" in stage["note"]

        assert len(side_effects.notifications) == 1
        assert "Đang xem xét" in side_effects.notifications[0]["content"]
        assert side_effects.events[0]["action"] == (
            ACTION_INTERVIEW_CANCELLED
        )
        assert side_effects.events[0]["to_status"] == (
            ApplicationStatus.UNDER_REVIEW
        )

    @pytest.mark.asyncio
    async def test_another_active_interview_keeps_application_interviewing(
        self, side_effects, monkeypatch
    ):
        application = make_application()
        interview = make_interview(application)
        other = SimpleNamespace(status=InterviewStatus.SCHEDULED)
        patch_recruiter_job(monkeypatch)
        service, _ = build_service(
            application, interview, remaining=[interview, other]
        )

        await service.cancel_interview(
            current_user=SimpleNamespace(id=uuid.uuid4()),
            interview_id=interview.id,
        )

        assert application.status == ApplicationStatus.INTERVIEWING
        service.applications.try_update_status.assert_not_awaited()
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_CANCELLED]
        assert side_effects.events[0]["to_status"] == (
            ApplicationStatus.INTERVIEWING
        )

    @pytest.mark.asyncio
    async def test_terminal_application_is_not_rewritten(
        self, side_effects, monkeypatch
    ):
        application = make_application(ApplicationStatus.OFFERED)
        interview = make_interview(application)
        patch_recruiter_job(monkeypatch)
        service, _ = build_service(
            application, interview, remaining=[interview]
        )

        await service.cancel_interview(
            current_user=SimpleNamespace(id=uuid.uuid4()),
            interview_id=interview.id,
        )

        assert application.status == ApplicationStatus.OFFERED
        service.applications.try_update_status.assert_not_awaited()
        service.interviews.list_by_application.assert_not_awaited()
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_CANCELLED]
        assert side_effects.events[0]["to_status"] == (
            ApplicationStatus.OFFERED
        )


class TestRecruiterInterviewLifecycleGuards:
    @staticmethod
    def _now() -> datetime:
        return datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def _patch_now(self, monkeypatch) -> datetime:
        now = self._now()
        monkeypatch.setattr(f"{MODULE}._utc_now", lambda: now)
        return now

    @staticmethod
    def _assert_no_side_effects(side_effects) -> None:
        assert side_effects.activities == []
        assert side_effects.events == []
        assert side_effects.notifications == []
        assert side_effects.emails == []

    @pytest.mark.asyncio
    async def test_cancelling_ended_interview_is_rejected_before_mutation(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(
            application, status=InterviewStatus.CANDIDATE_CONFIRMED
        )
        interview.scheduled_at = now - timedelta(hours=2)
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.cancel_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
            )

        assert interview.status is InterviewStatus.CANDIDATE_CONFIRMED
        assert application.status is ApplicationStatus.INTERVIEWING
        service.interviews.soft_delete.assert_not_awaited()
        service.interviews.list_by_application.assert_not_awaited()
        service.applications.try_update_status.assert_not_awaited()
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [
            InterviewStatus.COMPLETED,
            InterviewStatus.CANCELLED,
            InterviewStatus.CANDIDATE_DECLINED,
        ],
    )
    async def test_cancelling_terminal_interview_is_rejected(
        self, status, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application, status=status)
        interview.scheduled_at = now + timedelta(days=1)
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.cancel_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
            )

        assert interview.status is status
        service.interviews.soft_delete.assert_not_awaited()
        service.applications.try_update_status.assert_not_awaited()
        session.commit.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tz",
        [None, timezone(timedelta(hours=7))],
    )
    async def test_cancelling_at_exact_end_is_rejected_in_any_timezone(
        self, tz, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        scheduled_at = now - timedelta(minutes=60)
        interview.scheduled_at = (
            scheduled_at.replace(tzinfo=None)
            if tz is None
            else scheduled_at.astimezone(tz)
        )
        interview.duration_minutes = 60
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.cancel_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
            )

        assert interview.status is InterviewStatus.SCHEDULED
        service.interviews.soft_delete.assert_not_awaited()
        session.commit.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    async def test_cancelling_in_progress_interview_is_allowed(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        interview.scheduled_at = now - timedelta(minutes=30)
        interview.duration_minutes = 60
        other = SimpleNamespace(status=InterviewStatus.SCHEDULED)
        patch_recruiter_job(monkeypatch)
        service, session = build_service(
            application, interview, remaining=[other]
        )

        result = await service.cancel_interview(
            current_user=SimpleNamespace(id=uuid.uuid4()),
            interview_id=interview.id,
        )

        assert result.status is InterviewStatus.CANCELLED
        assert interview.status is InterviewStatus.CANCELLED
        service.interviews.soft_delete.assert_awaited_once_with(interview)
        service.applications.try_update_status.assert_not_awaited()
        session.commit.assert_awaited_once()
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_CANCELLED]
        assert side_effects.emails[0]["event"] == "cancelled"

    @pytest.mark.asyncio
    async def test_updating_ended_interview_without_scheduled_at_is_rejected(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        interview.scheduled_at = now - timedelta(hours=2)
        interview.notes = "original"
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.update_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
                data=make_update_data(notes="changed"),
            )

        assert interview.notes == "original"
        assert interview.scheduled_at == now - timedelta(hours=2)
        assert interview.status is InterviewStatus.SCHEDULED
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [
            InterviewStatus.COMPLETED,
            InterviewStatus.CANCELLED,
            InterviewStatus.CANDIDATE_DECLINED,
        ],
    )
    async def test_updating_terminal_interview_is_rejected(
        self, status, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application, status=status)
        interview.scheduled_at = now + timedelta(days=1)
        interview.notes = "original"
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.update_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
                data=make_update_data(notes="changed"),
            )

        assert interview.notes == "original"
        assert interview.status is status
        session.commit.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    async def test_updating_with_past_scheduled_at_is_rejected(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        interview.scheduled_at = now + timedelta(days=1)
        original_scheduled_at = interview.scheduled_at
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.update_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
                data=make_update_data(
                    scheduled_at=now - timedelta(hours=1)
                ),
            )

        assert interview.scheduled_at == original_scheduled_at
        session.commit.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    async def test_updating_upcoming_interview_succeeds(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        interview.scheduled_at = now + timedelta(days=1)
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])
        new_scheduled_at = now + timedelta(days=2)

        result = await service.update_interview(
            current_user=SimpleNamespace(id=uuid.uuid4()),
            interview_id=interview.id,
            data=make_update_data(
                scheduled_at=new_scheduled_at,
                duration_minutes=90,
                notes="Updated",
            ),
        )

        assert result is interview
        assert interview.scheduled_at == new_scheduled_at
        assert interview.duration_minutes == 90
        assert interview.notes == "Updated"
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        assert [
            row["action_type"] for row in side_effects.activities
        ] == [hiring.INTERVIEW_RESCHEDULED]
        assert side_effects.emails[0]["event"] == "rescheduled"
        assert side_effects.notifications[0]["notification_type"] == (
            "interview_updated"
        )
        assert side_effects.events[0]["action"] == ACTION_INTERVIEW_UPDATED

    @pytest.mark.asyncio
    async def test_updating_in_progress_interview_to_past_end_is_rejected(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        interview.scheduled_at = now - timedelta(minutes=30)
        interview.duration_minutes = 60
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        with pytest.raises(InvalidTransitionException):
            await service.update_interview(
                current_user=SimpleNamespace(id=uuid.uuid4()),
                interview_id=interview.id,
                data=make_update_data(duration_minutes=15),
            )

        assert interview.duration_minutes == 60
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()
        self._assert_no_side_effects(side_effects)

    @pytest.mark.asyncio
    async def test_updating_in_progress_interview_duration_is_allowed(
        self, side_effects, monkeypatch
    ):
        now = self._patch_now(monkeypatch)
        application = make_application()
        interview = make_interview(application)
        interview.scheduled_at = now - timedelta(minutes=30)
        interview.duration_minutes = 60
        patch_recruiter_job(monkeypatch)
        service, session = build_service(application, interview, remaining=[])

        await service.update_interview(
            current_user=SimpleNamespace(id=uuid.uuid4()),
            interview_id=interview.id,
            data=make_update_data(duration_minutes=90),
        )

        assert interview.duration_minutes == 90
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        assert side_effects.activities == []
        assert side_effects.emails == []
        assert side_effects.notifications[0]["notification_type"] == (
            "interview_updated"
        )
