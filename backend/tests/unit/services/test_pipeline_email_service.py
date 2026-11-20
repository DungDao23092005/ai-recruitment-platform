"""Unit tests for the pipeline email scheduler.

The real outbox is replaced with a spy so we can assert *what* would be
enqueued (event type, recipient, absence of private content) without a database
and without ever touching a provider.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.enums import ApplicationStatus
from app.services import pipeline_email_service as module


@pytest.fixture
def enqueue_spy(monkeypatch):
    calls = []

    async def _enqueue(session, **kwargs):
        calls.append(kwargs)
        return MagicMock()

    def _signal(session):
        return None

    monkeypatch.setattr(module, "enqueue_email", _enqueue)
    monkeypatch.setattr(module, "signal_dispatch_after_commit", _signal)
    return calls


class TestApplicationStatusEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [
            ApplicationStatus.OFFERED,
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
        ],
    )
    async def test_enqueues_for_outcome_statuses(self, enqueue_spy, status):
        await module.schedule_application_status_email(
            MagicMock(),
            to_email="candidate@example.com",
            job_title="Backend Engineer",
            new_status=status,
            idempotency_key=f"k-{status.value}",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_APPLICATION_STATUS
        assert call["to_email"] == "candidate@example.com"
        assert call["idempotency_key"] == f"k-{status.value}"
        assert "Backend Engineer" in call["html_body"]
        assert "Backend Engineer" in call["text_body"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [
            ApplicationStatus.APPLIED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.INTERVIEWING,
            ApplicationStatus.WITHDRAWN,
        ],
    )
    async def test_silent_for_non_outcome_statuses(self, enqueue_spy, status):
        await module.schedule_application_status_email(
            MagicMock(),
            to_email="candidate@example.com",
            job_title="Backend Engineer",
            new_status=status,
        )
        assert enqueue_spy == []

    @pytest.mark.asyncio
    async def test_silent_without_recipient(self, enqueue_spy):
        await module.schedule_application_status_email(
            MagicMock(),
            to_email=None,
            job_title="Backend Engineer",
            new_status=ApplicationStatus.OFFERED,
        )
        assert enqueue_spy == []


class TestInterviewEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event", ["scheduled", "rescheduled", "cancelled"])
    async def test_enqueues_lifecycle_events(self, enqueue_spy, event):
        await module.schedule_interview_email(
            MagicMock(),
            to_email="candidate@example.com",
            job_title="Backend Engineer",
            scheduled_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            event=event,
            idempotency_key=f"i-{event}",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_INTERVIEW_LIFECYCLE
        assert call["idempotency_key"] == f"i-{event}"

    @pytest.mark.asyncio
    async def test_rejects_unknown_event(self, enqueue_spy):
        with pytest.raises(ValueError):
            await module.schedule_interview_email(
                MagicMock(),
                to_email="candidate@example.com",
                job_title="Backend Engineer",
                scheduled_at=None,
                event="teleport",
            )
        assert enqueue_spy == []


class TestApplicationSubmissionEmail:
    @pytest.mark.asyncio
    async def test_enqueues_application_submission_email(self, enqueue_spy):
        await module.schedule_application_submission_email(
            MagicMock(),
            to_email="candidate@example.com",
            job_title="Backend Engineer",
            candidate_name="Nguyen Van A",
            idempotency_key="app-sub-123",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_APPLICATION_SUBMITTED
        assert call["to_email"] == "candidate@example.com"
        assert call["idempotency_key"] == "app-sub-123"
        assert "Backend Engineer" in call["html_body"]
        assert "Nguyen Van A" in call["html_body"]

    @pytest.mark.asyncio
    async def test_silent_without_recipient(self, enqueue_spy):
        await module.schedule_application_submission_email(
            MagicMock(),
            to_email=None,
            job_title="Backend Engineer",
        )
        assert enqueue_spy == []


class TestOfferResponseRecruiterEmail:
    @pytest.mark.asyncio
    async def test_enqueues_offer_accepted(self, enqueue_spy):
        await module.schedule_offer_response_recruiter_email(
            MagicMock(),
            to_email="recruiter@example.com",
            job_title="Backend Engineer",
            candidate_name="Nguyen Van A",
            action="accept",
            idempotency_key="offer-acc-1",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_OFFER_RESPONSE
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == "offer-acc-1"
        assert "chấp nhận" in call["html_body"]
        assert "Backend Engineer" in call["html_body"]

    @pytest.mark.asyncio
    async def test_enqueues_offer_declined(self, enqueue_spy):
        await module.schedule_offer_response_recruiter_email(
            MagicMock(),
            to_email="recruiter@example.com",
            job_title="Backend Engineer",
            candidate_name="Nguyen Van A",
            action="decline",
            idempotency_key="offer-dec-1",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_OFFER_RESPONSE
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == "offer-dec-1"
        assert "từ chối" in call["html_body"]

    @pytest.mark.asyncio
    async def test_silent_without_recipient(self, enqueue_spy):
        await module.schedule_offer_response_recruiter_email(
            MagicMock(),
            to_email=None,
            job_title="Backend Engineer",
            candidate_name="Nguyen Van A",
            action="accepted",
        )
        assert enqueue_spy == []


class TestInterviewDeclinedRecruiterEmail:
    @pytest.mark.asyncio
    async def test_enqueues_interview_declined_recruiter_email(self, enqueue_spy):
        await module.schedule_interview_declined_recruiter_email(
            MagicMock(),
            to_email="recruiter@example.com",
            job_title="Backend Engineer",
            candidate_name="Nguyen Van A",
            idempotency_key="int-dec-rec-1",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_INTERVIEW_DECLINED_RECRUITER
        assert call["to_email"] == "recruiter@example.com"
        assert call["idempotency_key"] == "int-dec-rec-1"
        assert "từ chối" in call["html_body"]
        assert "Backend Engineer" in call["html_body"]

    @pytest.mark.asyncio
    async def test_silent_without_recipient(self, enqueue_spy):
        await module.schedule_interview_declined_recruiter_email(
            MagicMock(),
            to_email=None,
            job_title="Backend Engineer",
        )
        assert enqueue_spy == []


class TestInterviewerAssignmentEmail:
    @pytest.mark.asyncio
    async def test_enqueues_interviewer_assignment_email(self, enqueue_spy):
        scheduled_at = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
        await module.schedule_interviewer_assignment_email(
            MagicMock(),
            to_email="interviewer@example.com",
            job_title="Backend Engineer",
            scheduled_at=scheduled_at,
            meeting_url="https://meet.google.com/xyz-abc",
            location="Room 101",
            idempotency_key="assign-1",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_INTERVIEWER_ASSIGNMENT
        assert call["to_email"] == "interviewer@example.com"
        assert call["idempotency_key"] == "assign-1"
        assert "Backend Engineer" in call["html_body"]
        assert "https://meet.google.com/xyz-abc" in call["html_body"]
        assert "Room 101" in call["html_body"]

    @pytest.mark.asyncio
    async def test_silent_without_recipient(self, enqueue_spy):
        await module.schedule_interviewer_assignment_email(
            MagicMock(),
            to_email=None,
            job_title="Backend Engineer",
        )
        assert enqueue_spy == []


class TestInterviewerScheduleChangeEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event", ["rescheduled", "cancelled"])
    async def test_enqueues_interviewer_schedule_change(self, enqueue_spy, event):
        scheduled_at = datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc)
        await module.schedule_interviewer_schedule_change_email(
            MagicMock(),
            to_email="interviewer@example.com",
            job_title="Backend Engineer",
            scheduled_at=scheduled_at,
            meeting_url="https://meet.example.com",
            event=event,
            idempotency_key=f"change-{event}",
        )

        assert len(enqueue_spy) == 1
        call = enqueue_spy[0]
        assert call["event_type"] == module.EVENT_INTERVIEWER_SCHEDULE_CHANGE
        assert call["to_email"] == "interviewer@example.com"
        assert call["idempotency_key"] == f"change-{event}"
        assert "Backend Engineer" in call["html_body"]

    @pytest.mark.asyncio
    async def test_rejects_unknown_event(self, enqueue_spy):
        with pytest.raises(ValueError):
            await module.schedule_interviewer_schedule_change_email(
                MagicMock(),
                to_email="interviewer@example.com",
                job_title="Backend Engineer",
                event="unknown_event",
            )
        assert enqueue_spy == []

    @pytest.mark.asyncio
    async def test_silent_without_recipient(self, enqueue_spy):
        await module.schedule_interviewer_schedule_change_email(
            MagicMock(),
            to_email=None,
            job_title="Backend Engineer",
            event="rescheduled",
        )
        assert enqueue_spy == []
