import uuid

import pytest

from tests.integration.api.conftest import API_V1

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
}


@pytest.fixture
def created_company(recruiter_client, run_async):
    resp = run_async(
        recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCompanies:
    def test_recruiter_creates_company(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Acme Corp"
        assert body["slug"] == "acme-corp"
        assert body["id"]
        assert body["created_at"]

    def test_candidate_cannot_create_company(
        self, candidate_client, run_async
    ):
        resp = run_async(
            candidate_client.post(f"{API_V1}/companies", json=COMPANY_BODY)
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_get_existing_company(
        self, recruiter_client, run_async, created_company
    ):
        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/companies/{created_company['id']}"
            )
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == created_company["id"]

    def test_get_nonexistent_company(self, recruiter_client, run_async):
        resp = run_async(
            recruiter_client.get(f"{API_V1}/companies/{uuid.uuid4()}")
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestJobs:
    def test_recruiter_creates_job(
        self, recruiter_client, run_async, created_company
    ):
        body = {**JOB_BODY, "company_id": created_company["id"]}
        resp = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 201
        job = resp.json()
        assert job["title"] == "Backend Engineer"
        assert job["status"] == "draft"
        assert job["id"]

    def test_create_job_nonexistent_company(
        self, recruiter_client, run_async
    ):
        body = {**JOB_BODY, "company_id": str(uuid.uuid4())}
        resp = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_candidate_cannot_create_job(self, candidate_client, run_async):
        body = {**JOB_BODY, "company_id": str(uuid.uuid4())}
        resp = run_async(
            candidate_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 403

    def test_list_jobs_returns_200(
        self, client, run_async, recruiter_client, created_company
    ):
        resp = run_async(client.get(f"{API_V1}/jobs"))

        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_published_job_visible(
        self, client, run_async, recruiter_client, created_company
    ):
        body = {**JOB_BODY, "company_id": created_company["id"], "status": "published"}
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))

        assert resp.status_code == 200
        assert resp.json()["id"] == job["id"]

    def test_published_job_in_list(
        self, client, run_async, recruiter_client, created_company
    ):
        body = {**JOB_BODY, "company_id": created_company["id"], "status": "published"}
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(client.get(f"{API_V1}/jobs"))

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert job["id"] in ids

    def test_draft_job_not_visible_by_id(
        self, client, run_async, recruiter_client, created_company
    ):
        body = {**JOB_BODY, "company_id": created_company["id"]}
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()
        assert job["status"] == "draft"

        resp = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"

    def test_closed_job_not_visible_by_id(
        self, client, run_async, recruiter_client, created_company
    ):
        body = {**JOB_BODY, "company_id": created_company["id"], "status": "closed"}
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"

    def test_draft_job_excluded_from_list(
        self, client, run_async, recruiter_client, created_company
    ):
        body = {**JOB_BODY, "company_id": created_company["id"]}
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(client.get(f"{API_V1}/jobs"))

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert job["id"] not in ids