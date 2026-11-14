from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.database.session import async_session_factory
from app.models import Application, Interview
from tests.integration.api.conftest import API_V1, apply_job_with_resume

RECRUITER_SECRET_NOTE = "CONFIDENTIAL: Internal recruiter deliberation notes"


def _schedule_interview(
    recruiter_client,
    run_async,
    application_id: str,
    *,
    scheduled_at: str | None = None,
    location: str | None = "Room A",
    meeting_url: str | None = "https://meet.example.com/interview-1",
    notes: str = RECRUITER_SECRET_NOTE,
) -> dict:
    if scheduled_at is None:
        scheduled_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    resp = run_async(
        recruiter_client.post(
            f"{API_V1}/applications/{application_id}/interviews",
            json={
                "scheduled_at": scheduled_at,
                "duration_minutes": 45,
                "interview_type": "technical",
                "location": location,
                "meeting_url": meeting_url,
                "notes": notes,
            },
        )
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_job_for_recruiter(recruiter_client, run_async) -> tuple[dict, dict]:
    slug = f"cand-sched-{uuid.uuid4().hex[:8]}"
    company = run_async(
        recruiter_client.post(
            f"{API_V1}/companies",
            json={
                "name": "Target Tech Corp",
                "slug": slug,
                "tax_code": f"TAX-{uuid.uuid4().hex[:8]}",
                "size": "startup",
            },
        )
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs",
            json={
                "title": "Lead Platform Engineer",
                "description": "Design resilient systems",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Da Nang",
                "status": "published",
                "company_id": company["id"],
            },
        )
    ).json()
    return company, job


def _setup_candidate_application(candidate_client, run_async, job_id: str) -> dict:
    run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Applicant Alice", "title": "Senior Engineer"},
        )
    )
    application = apply_job_with_resume(candidate_client, run_async, job_id).json()
    return application


class TestCandidateInterviewsAPI:
    def test_candidate_retrieves_own_interviews(
        self, candidate_client, recruiter_client, run_async
    ):
        company, job = _setup_job_for_recruiter(recruiter_client, run_async)
        application = _setup_candidate_application(candidate_client, run_async, job["id"])
        created = _schedule_interview(recruiter_client, run_async, application["id"])

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        item = data[0]
        assert item["id"] == created["id"]
        assert item["application_id"] == application["id"]
        assert item["job_id"] == job["id"]
        assert item["job_title"] == "Lead Platform Engineer"
        assert item["company_name"] == "Target Tech Corp"
        assert item["status"] == "scheduled"
        assert item["duration_minutes"] == 45
        assert item["interview_type"] == "technical"
        assert item["meeting_url"] == "https://meet.example.com/interview-1"
        assert item["location"] == "Room A"

    def test_candidate_isolation_candidate_a_cannot_see_candidate_b(
        self, candidate_client, candidate_b_client, recruiter_client, run_async
    ):
        _, job = _setup_job_for_recruiter(recruiter_client, run_async)
        app_a = _setup_candidate_application(candidate_client, run_async, job["id"])
        _schedule_interview(recruiter_client, run_async, app_a["id"])

        run_async(
            candidate_b_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Applicant Bob", "title": "Backend Dev"},
            )
        )

        resp_b = run_async(candidate_b_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp_b.status_code == 200, resp_b.text
        assert resp_b.json() == []

    def test_candidate_without_interviews_receives_empty_list(
        self, candidate_client, recruiter_client, run_async
    ):
        _, job = _setup_job_for_recruiter(recruiter_client, run_async)
        _setup_candidate_application(candidate_client, run_async, job["id"])

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_candidate_with_no_profile_returns_empty_list(
        self, candidate_b_client, run_async
    ):
        resp = run_async(candidate_b_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_deleted_applications_are_excluded(
        self, candidate_client, recruiter_client, run_async
    ):
        _, job = _setup_job_for_recruiter(recruiter_client, run_async)
        app = _setup_candidate_application(candidate_client, run_async, job["id"])
        _schedule_interview(recruiter_client, run_async, app["id"])

        async def _soft_del():
            async with async_session_factory() as session:
                await session.execute(
                    update(Application)
                    .where(Application.id == uuid.UUID(app["id"]))
                    .values(is_deleted=True)
                )
                await session.commit()

        run_async(_soft_del())

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_deleted_interviews_are_excluded(
        self, candidate_client, recruiter_client, run_async
    ):
        _, job = _setup_job_for_recruiter(recruiter_client, run_async)
        app = _setup_candidate_application(candidate_client, run_async, job["id"])
        interview = _schedule_interview(recruiter_client, run_async, app["id"])

        async def _soft_del():
            async with async_session_factory() as session:
                await session.execute(
                    update(Interview)
                    .where(Interview.id == uuid.UUID(interview["id"]))
                    .values(is_deleted=True)
                )
                await session.commit()

        run_async(_soft_del())

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_recruiter_notes_are_never_exposed(
        self, candidate_client, recruiter_client, run_async
    ):
        _, job = _setup_job_for_recruiter(recruiter_client, run_async)
        app = _setup_candidate_application(candidate_client, run_async, job["id"])
        _schedule_interview(
            recruiter_client,
            run_async,
            app["id"],
            notes=RECRUITER_SECRET_NOTE,
        )

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        assert RECRUITER_SECRET_NOTE not in resp.text
        item = resp.json()[0]
        assert "notes" not in item
        assert "scorecards" not in item
        assert "evaluations" not in item
        assert "assignments" not in item

    def test_unauthenticated_requests_return_401(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 401, resp.text

    def test_recruiter_cannot_access_candidate_schedule_returns_403(
        self, recruiter_client, run_async
    ):
        resp = run_async(recruiter_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 403, resp.text

    def test_static_route_resolves_without_uuid_error(
        self, candidate_client, run_async
    ):
        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine/interviews"))
        assert resp.status_code == 200, resp.text
        assert resp.status_code != 422

    def test_candidate_cannot_act_on_another_candidates_interview(
        self, candidate_client, candidate_b_client, recruiter_client, run_async
    ):
        _, job = _setup_job_for_recruiter(recruiter_client, run_async)
        app_a = _setup_candidate_application(candidate_client, run_async, job["id"])
        interview_a = _schedule_interview(recruiter_client, run_async, app_a["id"])

        run_async(
            candidate_b_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Bob", "title": "Dev"},
            )
        )

        resp = run_async(
            candidate_b_client.patch(
                f"{API_V1}/applications/{app_a['id']}/interviews/{interview_a['id']}/action",
                json={"action": "confirm"},
            )
        )
        assert resp.status_code == 404, resp.text
