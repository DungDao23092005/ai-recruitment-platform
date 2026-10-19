"""API coverage for private interview scorecards.

Each evaluator has at most one active scorecard per interview (duplicate create
is a 409, re-submission is a PATCH). Evaluations are recruiter/admin only, scoped
to an application, and never visible to candidates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Eval Corp",
    "slug": "eval-corp",
    "tax_code": "443322110",
    "size": "startup",
}

JOB_BODY = {
    "title": "Data Engineer",
    "description": "Own the data platform",
    "job_type": "full_time",
    "workplace_type": "hybrid",
    "location": "Da Nang",
    "status": "published",
}


def _create_application(recruiter_client, candidate_client, run_async):
    suffix = uuid.uuid4().hex[:8]
    company = run_async(
        recruiter_client.post(
            f"{API_V1}/companies",
            json={
                **COMPANY_BODY,
                "name": f"Eval Corp {suffix}",
                "slug": f"eval-corp-{suffix}",
                "tax_code": str(uuid.uuid4().int)[:12],
            },
        )
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs", json={**JOB_BODY, "company_id": company["id"]}
        )
    ).json()
    application = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job["id"]}
        )
    ).json()
    return application, job


@pytest.fixture
def evaluated(recruiter_client, candidate_client, run_async):
    run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Eval Candidate", "title": "Engineer"},
        )
    )
    application, job = _create_application(
        recruiter_client, candidate_client, run_async
    )
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    interview = run_async(
        recruiter_client.post(
            f"{API_V1}/applications/{application['id']}/interviews",
            json={
                "scheduled_at": scheduled_at,
                "duration_minutes": 45,
                "interview_type": "technical",
                "location": "Room 2",
            },
        )
    ).json()
    return {
        "application": application,
        "job": job,
        "interview": interview,
        "recruiter_client": recruiter_client,
        "candidate_client": candidate_client,
        "run_async": run_async,
    }


def _eval_url(application_id, interview_id):
    return (
        f"{API_V1}/applications/{application_id}/interviews/"
        f"{interview_id}/evaluations"
    )


class TestEvaluationCreateAndUpdate:
    def test_create_then_duplicate_conflicts(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        created = run_async(
            client.post(
                _eval_url(app_id, interview_id),
                json={"rating": 5, "recommendation": "strong_hire"},
            )
        )
        assert created.status_code == 201, created.text
        evaluation = created.json()
        assert evaluation["rating"] == 5
        assert evaluation["interview_id"] == interview_id
        assert evaluation["application_id"] == app_id

        duplicate = run_async(
            client.post(
                _eval_url(app_id, interview_id),
                json={"rating": 3},
            )
        )
        assert duplicate.status_code == 409, duplicate.text

    def test_update_replaces_rating(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        evaluation = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 2})
        ).json()

        updated = run_async(
            client.patch(
                f"{API_V1}/applications/{app_id}/evaluations/{evaluation['id']}",
                json={"rating": 4, "recommendation": "hire"},
            )
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["rating"] == 4
        assert updated.json()["recommendation"] == "hire"

    def test_delete_then_resubmit(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        evaluation = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 3})
        ).json()

        deleted = run_async(
            client.delete(
                f"{API_V1}/applications/{app_id}/evaluations/{evaluation['id']}"
            )
        )
        assert deleted.status_code == 204, deleted.text

        again = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 5})
        )
        assert again.status_code == 201, again.text

    def test_list_by_interview_and_application(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        evaluation = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 4})
        ).json()

        by_interview = run_async(client.get(_eval_url(app_id, interview_id)))
        assert by_interview.status_code == 200, by_interview.text
        assert [e["id"] for e in by_interview.json()] == [evaluation["id"]]

        by_application = run_async(
            client.get(f"{API_V1}/applications/{app_id}/evaluations")
        )
        assert by_application.status_code == 200, by_application.text
        assert [e["id"] for e in by_application.json()] == [evaluation["id"]]


class TestEvaluationValidation:
    def test_rating_out_of_range_rejected(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        low = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 0})
        )
        assert low.status_code == 422, low.text
        high = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 6})
        )
        assert high.status_code == 422, high.text

    def test_unknown_recommendation_rejected(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        resp = run_async(
            client.post(
                _eval_url(app_id, interview_id),
                json={"rating": 3, "recommendation": "maybe"},
            )
        )
        assert resp.status_code == 422, resp.text


class TestEvaluationIsolation:
    def test_candidate_cannot_access_evaluations(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        candidate = evaluated["candidate_client"]

        resp = run_async(candidate.get(_eval_url(app_id, interview_id)))
        assert resp.status_code == 403, resp.text

    def test_foreign_recruiter_gets_404(
        self, evaluated, recruiter_b_client, run_async
    ):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]

        resp = run_async(
            recruiter_b_client.post(
                _eval_url(app_id, interview_id), json={"rating": 5}
            )
        )
        assert resp.status_code == 404, resp.text

    def test_unknown_interview_is_404(self, evaluated, run_async):
        app_id = evaluated["application"]["id"]
        client = evaluated["recruiter_client"]
        resp = run_async(
            client.post(_eval_url(app_id, uuid.uuid4()), json={"rating": 5})
        )
        assert resp.status_code == 404, resp.text

    def test_evaluation_scoped_to_application(
        self, evaluated, recruiter_client, candidate_client, run_async
    ):
        app_id = evaluated["application"]["id"]
        interview_id = evaluated["interview"]["id"]
        client = evaluated["recruiter_client"]

        evaluation = run_async(
            client.post(_eval_url(app_id, interview_id), json={"rating": 4})
        ).json()

        # A second application for the same company must not expose the first
        # application's evaluation through its own path. A recruiter owns one
        # company, so we add a second job under it instead of a second company.
        other_job = run_async(
            recruiter_client.post(
                f"{API_V1}/jobs",
                json={
                    **JOB_BODY,
                    "title": "Data Engineer II",
                    "company_id": evaluated["job"]["company_id"],
                },
            )
        ).json()
        other_application = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": other_job["id"]}
            )
        ).json()
        resp = run_async(
            client.patch(
                f"{API_V1}/applications/{other_application['id']}/evaluations/"
                f"{evaluation['id']}",
                json={"rating": 1},
            )
        )
        assert resp.status_code == 404, resp.text
