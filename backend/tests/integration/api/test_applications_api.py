import uuid

import pytest

from tests.integration.api.conftest import API_V1, PASSWORD

COMPANY_BODY = {
    "name": "Acme Corp",
    "slug": "acme-corp",
    "tax_code": "123456789",
    "size": "startup",
}

JOB_BODY = {
    "title": "Backend Engineer",
    "description": "Build robust APIs",
    "job_type": "full_time",
    "workplace_type": "remote",
    "location": "Ho Chi Minh",
    "status": "published",
}


@pytest.fixture
def published_job(recruiter_client, run_async):
    company = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    ).json()
    job = run_async(
        recruiter_client.post(
            f"{API_V1}/jobs",
            json={**JOB_BODY, "company_id": company["id"]},
        )
    ).json()
    return job


def create_candidate_profile(candidate_client, run_async):
    return run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Jane Doe", "title": "Engineer"},
        )
    )


class TestCandidateProfile:
    def test_create_candidate_profile(self, candidate_client, run_async):
        resp = create_candidate_profile(candidate_client, run_async)

        assert resp.status_code == 201
        body = resp.json()
        assert body["full_name"] == "Jane Doe"
        assert body["user_id"]

    def test_duplicate_profile_returns_400(
        self, candidate_client, run_async
    ):
        first = create_candidate_profile(candidate_client, run_async)
        assert first.status_code == 201

        second = create_candidate_profile(candidate_client, run_async)

        assert second.status_code == 400
        assert "already has a candidate profile" in second.json()["detail"]


class TestApplyJob:
    def test_candidate_applies_successfully(
        self, candidate_client, run_async, published_job
    ):
        create_candidate_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["job_id"] == published_job["id"]
        assert body["status"] == "applied"

    def test_candidate_without_profile_returns_400(
        self, candidate_client, run_async, published_job
    ):
        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Candidate profile required"

    def test_duplicate_application_returns_400(
        self, candidate_client, run_async, published_job
    ):
        create_candidate_profile(candidate_client, run_async)
        first = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )
        assert first.status_code == 201

        second = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        )

        assert second.status_code == 400
        assert "already applied" in second.json()["detail"]

    def test_nonexistent_job_returns_404(
        self, candidate_client, run_async
    ):
        create_candidate_profile(candidate_client, run_async)

        resp = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": str(uuid.uuid4())},
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestApplicationStatusUpdate:
    def test_recruiter_updates_status(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "under_review"

    def test_invalid_transition_returns_400(
        self,
        candidate_client,
        recruiter_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "accepted"},
            )
        )

        assert resp.status_code == 400
        assert "Invalid Application status transition" in resp.json()["detail"]

    def test_candidate_cannot_update_status(
        self,
        candidate_client,
        run_async,
        published_job,
    ):
        create_candidate_profile(candidate_client, run_async)
        application = run_async(
            candidate_client.post(
                f"{API_V1}/applications",
                json={"job_id": published_job["id"]},
            )
        ).json()

        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/applications/{application['id']}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_nonexistent_application_returns_404(
        self, recruiter_client, run_async
    ):
        resp = run_async(
            recruiter_client.patch(
                f"{API_V1}/applications/{uuid.uuid4()}/status",
                json={"status": "under_review"},
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]