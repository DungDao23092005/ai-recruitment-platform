from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.integration.api.conftest import API_V1


def _company_body() -> dict:
    suffix = uuid.uuid4().hex[:8]
    return {
        "name": f"Target Co {suffix}",
        "slug": f"target-co-{suffix}",
        "tax_code": str(uuid.uuid4().int)[:9],
        "size": "startup",
    }


def _create_application(recruiter_client, candidate_client, run_async) -> dict:
    company = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=_company_body())
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs",
            json={
                "title": "Backend Engineer",
                "description": "Build robust APIs",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Ho Chi Minh",
                "status": "published",
                "company_id": company["id"],
            },
        )
    ).json()
    profile = run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Jane Doe", "title": "Engineer"},
        )
    )
    assert profile.status_code == 201, profile.text
    application = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job["id"]}
        )
    ).json()
    return application


class TestCandidateApplicationTarget:
    def test_candidate_gets_own_application_with_interviews(
        self,
        candidate_client,
        recruiter_client,
        run_async,
    ):
        application = _create_application(
            recruiter_client, candidate_client, run_async
        )
        scheduled_at = (
            datetime.now(timezone.utc) + timedelta(days=2)
        ).isoformat()
        interview = run_async(
            recruiter_client.post(
                f"{API_V1}/applications/{application['id']}/interviews",
                json={
                    "scheduled_at": scheduled_at,
                    "duration_minutes": 60,
                    "interview_type": "technical",
                    "location": "Room 1",
                },
            )
        )
        assert interview.status_code == 201, interview.text

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine/{application['id']}"
            )
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == application["id"]
        assert body["job_title"] == "Backend Engineer"
        assert body["company_name"].startswith("Target Co")
        assert body["status"] == "interviewing"
        assert [item["id"] for item in body["interviews"]] == [
            interview.json()["id"]
        ]
        assert "notes" not in body["interviews"][0]

    def test_other_candidate_gets_404(
        self,
        candidate_client,
        candidate_b_client,
        recruiter_client,
        run_async,
    ):
        application = _create_application(
            recruiter_client, candidate_client, run_async
        )

        resp = run_async(
            candidate_b_client.get(
                f"{API_V1}/applications/mine/{application['id']}"
            )
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Application {application['id']} not found"
        )

    def test_nonexistent_application_gets_404(
        self,
        candidate_client,
        run_async,
    ):
        run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Jane Doe", "title": "Engineer"},
            )
        )

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine/{uuid.uuid4()}"
            )
        )

        assert resp.status_code == 404

    def test_recruiter_gets_403(
        self,
        recruiter_client,
        run_async,
    ):
        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/applications/mine/{uuid.uuid4()}"
            )
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(
            client.get(f"{API_V1}/applications/mine/{uuid.uuid4()}")
        )

        assert resp.status_code == 401
