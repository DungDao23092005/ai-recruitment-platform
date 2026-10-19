"""API coverage for application history and the candidate-visible timeline.

* recruiter/admin history exposes actor, status diff and internal metadata;
* the candidate timeline is a *filtered* projection that never contains internal
  notes, private evaluations, actor identities or metadata;
* every status change / interview event is recorded atomically and, for outcome
  statuses, durably enqueues exactly one outbox row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.models import EmailOutbox
from app.services.pipeline_email_service import (
    EVENT_APPLICATION_STATUS,
    EVENT_INTERVIEW_LIFECYCLE,
)
from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Activity Corp",
    "slug": "activity-corp",
    "tax_code": "112233445",
    "size": "startup",
}

JOB_BODY = {
    "title": "Platform Engineer",
    "description": "Keep the pipeline observable",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Remote",
    "status": "published",
}

RECRUITER_NOTE = "INTERNAL ONLY: negotiate hard on salary"


@pytest.fixture
def pipeline(recruiter_client, candidate_client, run_async):
    company = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs", json={**JOB_BODY, "company_id": company["id"]}
        )
    ).json()
    run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Activity Candidate", "title": "Engineer"},
        )
    )
    application = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job["id"]}
        )
    ).json()
    return {"application": application, "job": job}


def _set_status(client, run_async, application_id, value):
    return run_async(
        client.patch(
            f"{API_V1}/applications/{application_id}/status",
            json={"status": value},
        )
    )


def _schedule_interview(client, run_async, application_id):
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp = run_async(
        client.post(
            f"{API_V1}/applications/{application_id}/interviews",
            json={
                "scheduled_at": scheduled_at,
                "duration_minutes": 60,
                "interview_type": "technical",
                "location": "Room 9",
            },
        )
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _outbox_rows():
    async with async_session_factory() as session:
        return list(
            (await session.execute(select(EmailOutbox))).scalars().all()
        )


class TestRecruiterActivityHistory:
    def test_status_change_is_recorded_with_actor(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        assert _set_status(recruiter_client, run_async, app_id, "under_review").status_code == 200

        resp = run_async(
            recruiter_client.get(f"{API_V1}/applications/{app_id}/activities")
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["action_type"] == "status_changed"
        assert row["from_status"] == "applied"
        assert row["to_status"] == "under_review"
        assert row["actor_id"]

    def test_interview_events_are_recorded(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        _schedule_interview(recruiter_client, run_async, app_id)

        resp = run_async(
            recruiter_client.get(f"{API_V1}/applications/{app_id}/activities")
        )
        actions = {row["action_type"] for row in resp.json()}
        assert "interview_scheduled" in actions
        assert "status_changed" in actions

    def test_pagination_bound_is_enforced(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/applications/{app_id}/activities",
                params={"limit": 101},
            )
        )
        assert resp.status_code == 422, resp.text

    def test_foreign_recruiter_gets_404(self, pipeline, recruiter_b_client, run_async):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            recruiter_b_client.get(f"{API_V1}/applications/{app_id}/activities")
        )
        assert resp.status_code == 404, resp.text


class TestCandidateTimeline:
    def test_timeline_excludes_actor_note_and_metadata(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        app_id = pipeline["application"]["id"]
        _set_status(recruiter_client, run_async, app_id, "under_review")
        run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{app_id}/notes",
                json={"content": RECRUITER_NOTE},
            )
        )

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine/{app_id}/timeline"
            )
        )
        assert resp.status_code == 200, resp.text
        assert RECRUITER_NOTE not in resp.text
        rows = resp.json()
        assert [row["action_type"] for row in rows] == ["status_changed"]
        for row in rows:
            assert set(row) == {
                "id",
                "action_type",
                "from_status",
                "to_status",
                "created_at",
            }

    def test_timeline_includes_interview_lifecycle(
        self, pipeline, recruiter_client, candidate_client, run_async
    ):
        app_id = pipeline["application"]["id"]
        interview = _schedule_interview(recruiter_client, run_async, app_id)

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine/{app_id}/timeline"
            )
        )
        actions = {row["action_type"] for row in resp.json()}
        assert "interview_scheduled" in actions

        confirm = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/{app_id}/interviews/"
                f"{interview['id']}/action",
                json={"action": "confirm"},
            )
        )
        assert confirm.status_code == 200, confirm.text

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine/{app_id}/timeline"
            )
        )
        actions = {row["action_type"] for row in resp.json()}
        assert "interview_confirmed" in actions

    def test_withdrawal_is_recorded_on_timeline(
        self, pipeline, candidate_client, run_async
    ):
        app_id = pipeline["application"]["id"]
        withdraw = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/mine/{app_id}/withdraw"
            )
        )
        assert withdraw.status_code == 200, withdraw.text

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine/{app_id}/timeline"
            )
        )
        actions = {row["action_type"] for row in resp.json()}
        assert "candidate_withdrew" in actions

    def test_other_candidate_cannot_read_timeline(
        self, pipeline, candidate_b_client, run_async
    ):
        app_id = pipeline["application"]["id"]
        resp = run_async(
            candidate_b_client.get(
                f"{API_V1}/applications/mine/{app_id}/timeline"
            )
        )
        assert resp.status_code == 404, resp.text


class TestOutboxAtomicity:
    def test_invalid_transition_writes_nothing(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        # applied -> offered is not a canonical/domain transition.
        resp = _set_status(recruiter_client, run_async, app_id, "offered")
        assert resp.status_code == 400, resp.text

        activities = run_async(
            recruiter_client.get(f"{API_V1}/applications/{app_id}/activities")
        )
        assert activities.json() == []
        assert run_async(_outbox_rows()) == []

    def test_offered_enqueues_single_outbox_row(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        for value in ("under_review", "shortlisted", "interviewing", "offered"):
            resp = _set_status(recruiter_client, run_async, app_id, value)
            assert resp.status_code == 200, resp.text

        rows = run_async(_outbox_rows())
        assert len(rows) == 1
        row = rows[0]
        assert row.event_type == EVENT_APPLICATION_STATUS
        assert row.idempotency_key.endswith(":offered")
        assert "@example.com" in row.to_email

    def test_intermediate_status_does_not_email(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        for value in ("under_review", "shortlisted", "interviewing"):
            assert _set_status(recruiter_client, run_async, app_id, value).status_code == 200
        assert run_async(_outbox_rows()) == []

    def test_interview_scheduled_enqueues_outbox_row(self, pipeline, recruiter_client, run_async):
        app_id = pipeline["application"]["id"]
        _schedule_interview(recruiter_client, run_async, app_id)

        rows = run_async(_outbox_rows())
        assert len(rows) == 1
        assert rows[0].event_type == EVENT_INTERVIEW_LIFECYCLE
