"""Regression: recruiter-only interview notes must never reach candidates.

Covers the candidate-facing ``GET /applications/mine`` list and the candidate
interview action endpoint. The recruiter-facing endpoints must keep exposing the
internal notes, proving the fix is a targeted projection split rather than a
global removal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Privacy Corp",
    "slug": "privacy-corp",
    "tax_code": "998877665",
    "size": "startup",
}

JOB_BODY = {
    "title": "Security Engineer",
    "description": "Keep candidate data private",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}

RECRUITER_NOTES = "INTERNAL ONLY: strong hire signal, keep between recruiters"
CANDIDATE_NOTES = "I can attend."


@pytest.fixture
def candidate_application(recruiter_client, candidate_client, run_async):
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
            json={"full_name": "Private Candidate", "title": "Engineer"},
        )
    )
    application = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job["id"]}
        )
    ).json()
    return {"application": application, "job": job}


def _schedule_interview(recruiter_client, run_async, application_id):
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp = run_async(
        recruiter_client.post(
            f"{API_V1}/applications/{application_id}/interviews",
            json={
                "scheduled_at": scheduled_at,
                "duration_minutes": 60,
                "interview_type": "technical",
                "location": "Room 1",
                "notes": RECRUITER_NOTES,
            },
        )
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["notes"] == RECRUITER_NOTES
    return resp.json()


class TestCandidateInterviewPrivacy:
    def test_mine_list_excludes_recruiter_notes(
        self, candidate_application, recruiter_client, candidate_client, run_async
    ):
        application = candidate_application["application"]
        _schedule_interview(recruiter_client, run_async, application["id"])

        resp = run_async(candidate_client.get(f"{API_V1}/applications/mine"))

        assert resp.status_code == 200, resp.text
        body = resp.text
        assert RECRUITER_NOTES not in body
        items = resp.json()
        assert len(items) == 1
        interviews = items[0]["interviews"]
        assert len(interviews) == 1
        assert "notes" not in interviews[0]
        assert "candidate_notes" in interviews[0]
        assert interviews[0]["location"] == "Room 1"

    def test_mine_filtered_by_job_excludes_recruiter_notes(
        self, candidate_application, recruiter_client, candidate_client, run_async
    ):
        application = candidate_application["application"]
        job = candidate_application["job"]
        _schedule_interview(recruiter_client, run_async, application["id"])

        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/mine", params={"job_id": job["id"]}
            )
        )

        assert resp.status_code == 200, resp.text
        assert RECRUITER_NOTES not in resp.text
        assert "notes" not in resp.json()[0]["interviews"][0]

    def test_candidate_action_response_excludes_recruiter_notes(
        self, candidate_application, recruiter_client, candidate_client, run_async
    ):
        application = candidate_application["application"]
        interview = _schedule_interview(
            recruiter_client, run_async, application["id"]
        )

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/{application['id']}/interviews/"
                f"{interview['id']}/action",
                json={"action": "confirm", "candidate_notes": CANDIDATE_NOTES},
            )
        )

        assert resp.status_code == 200, resp.text
        assert RECRUITER_NOTES not in resp.text
        payload = resp.json()
        assert "notes" not in payload
        assert payload["candidate_notes"] == CANDIDATE_NOTES
        assert payload["status"] == "candidate_confirmed"


class TestRecruiterInterviewStillExposesNotes:
    def test_application_detail_keeps_recruiter_notes(
        self, candidate_application, recruiter_client, run_async
    ):
        application = candidate_application["application"]
        _schedule_interview(recruiter_client, run_async, application["id"])

        resp = run_async(
            recruiter_client.get(f"{API_V1}/applications/{application['id']}")
        )

        assert resp.status_code == 200, resp.text
        interviews = resp.json()["interviews"]
        assert len(interviews) == 1
        assert interviews[0]["notes"] == RECRUITER_NOTES

    def test_recruiter_interview_list_keeps_notes(
        self, candidate_application, recruiter_client, run_async
    ):
        application = candidate_application["application"]
        _schedule_interview(recruiter_client, run_async, application["id"])

        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/applications/{application['id']}/interviews"
            )
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["notes"] == RECRUITER_NOTES
