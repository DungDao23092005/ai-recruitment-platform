from __future__ import annotations

import uuid

import httpx
import pytest
from tests.integration.api.conftest import API_V1, PASSWORD, run

from app.main import app
from app.domain.enums import JobStatus, JobType, WorkplaceType
from app.models import Company, Job, User


def _make_auth_client(client: httpx.AsyncClient, role: str) -> httpx.AsyncClient:
    email = f"{role}-{uuid.uuid4()}@example.com"
    register = run(
        client.post(
            f"{API_V1}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
        )
    )
    assert register.status_code == 201, register.text
    login = run(
        client.post(
            f"{API_V1}/auth/login",
            data={"username": email, "password": PASSWORD},
        )
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
def company(admin_client):
    # Create a company for the admin
    resp = run(admin_client.post(
        f"{API_V1}/companies",
        json={
            "name": "Test Company",
            "slug": "test-company",
            "tax_code": "123456789",
            "size": "sme",
        },
    ))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def jobs(admin_client, company):
    job_ids = []
    for title in ["Senior Python Developer", "Frontend Developer", "DevOps Engineer"]:
        resp = run(admin_client.post(
            f"{API_V1}/jobs",
            json={
                "company_id": company["id"],
                "title": title,
                "description": f"Build {title} applications",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Ho Chi Minh City",
            },
        ))
        assert resp.status_code == 201, resp.text
        job_ids.append(resp.json()["id"])
    return job_ids


class TestAdminJobsAuthorization:
    def test_anonymous_users_401(self, client):
        resp = run(client.get(f"{API_V1}/admin/jobs"))
        assert resp.status_code == 401, resp.text

    def test_candidate_forbidden(self, candidate_client):
        resp = run(candidate_client.get(f"{API_V1}/admin/jobs"))
        assert resp.status_code == 403

    def test_recruiter_forbidden(self, recruiter_client):
        resp = run(recruiter_client.get(f"{API_V1}/admin/jobs"))
        assert resp.status_code == 403


class TestAdminJobsList:
    def test_admin_sees_all_jobs(self, admin_client, company, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["skip"] == 0
        assert data["limit"] == 10

    def test_pagination_skip_0_limit_2(self, admin_client, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?skip=0&limit=2"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["skip"] == 0
        assert data["limit"] == 2

    def test_pagination_skip_10_limit_10(self, admin_client, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?skip=10&limit=10"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 0
        assert data["skip"] == 10
        assert data["limit"] == 10

    def test_search_filters_jobs(self, admin_client, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?search=Python"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert "Python" in data["items"][0]["title"]

    def test_search_case_insensitive(self, admin_client, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?search=python"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_search_with_pagination(self, admin_client, company):
        # Create more jobs with "Developer" in title
        for i in range(5):
            resp = run(admin_client.post(
                f"{API_V1}/jobs",
                json={
                    "company_id": company["id"],
                    "title": f"Developer {i}",
                    "description": f"Dev job {i}",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "location": "Remote",
                },
            ))
            assert resp.status_code == 201, resp.text

        # Search for "Developer" with pagination
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?search=Developer&skip=0&limit=3"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 3
        assert data["skip"] == 0
        assert data["limit"] == 3

        # Second page
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?search=Developer&skip=3&limit=3"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["skip"] == 3
        assert data["limit"] == 3


class TestAdminJobsContract:
    def test_recruiter_mine_contract_unchanged(self, recruiter_client, company):
        """Ensure /jobs/mine still works for recruiters and returns Job[]"""
        # Create a job for the recruiter's company
        resp = run(recruiter_client.post(
            f"{API_V1}/jobs",
            json={
                "company_id": company["id"],
                "title": "Recruiter Job",
                "description": "Test job for recruiter",
                "job_type": "full_time",
                "workplace_type": "remote",
                "location": "Remote",
            },
        ))
        # If recruiter doesn't own the company, this might return 403 or 400
        # The important thing is that /jobs/mine returns a list (not an error)
        resp = run(recruiter_client.get(f"{API_V1}/jobs/mine"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # The list might be empty if recruiter doesn't own the company
        # The key assertion is that it returns a list, not an error

    def test_recruiter_mine_pagination_works(self, recruiter_client, company):
        resp = run(recruiter_client.get(f"{API_V1}/jobs/mine?skip=0&limit=2"))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_admin_jobs_returns_items_and_total(self, admin_client, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs"))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data
        assert isinstance(data["total"], int)
        assert isinstance(data["items"], list)

    def test_empty_search_returns_all_jobs(self, admin_client, jobs):
        resp = run(admin_client.get(f"{API_V1}/admin/jobs?search="))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3