import uuid

import pytest
from fastapi import Depends
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.main import app
from app.models import Job
from tests.integration.api.conftest import API_V1, apply_job_with_resume

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


async def count_jobs_for_company(company_id: str) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.company_id == company_id)
        )
        return int(result.scalar_one())


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

    def test_list_companies_includes_created(
        self, recruiter_client, run_async, created_company
    ):
        resp = run_async(recruiter_client.get(f"{API_V1}/companies"))

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        ids = [company["id"] for company in body]
        assert created_company["id"] in ids

    def test_list_companies_returns_empty(self, recruiter_client, run_async):
        resp = run_async(recruiter_client.get(f"{API_V1}/companies"))

        assert resp.status_code == 200
        assert resp.json() == []


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
        data = resp.json()
        assert isinstance(data, dict)
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)

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
        ids = [item["id"] for item in resp.json()["items"]]
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
        ids = [item["id"] for item in resp.json()["items"]]
        assert job["id"] not in ids


class TestCompanyOwnership:
    """Security: recruiter-company ownership isolation (backend enforced)."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_recruiter_a_sees_only_own_company(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )

        list_a = run_async(
            recruiter_a_client.get(f"{API_V1}/companies")
        ).json()
        list_b = run_async(
            recruiter_b_client.get(f"{API_V1}/companies")
        ).json()

        ids_a = [c["id"] for c in list_a]
        ids_b = [c["id"] for c in list_b]
        assert company_a["id"] in ids_a
        assert company_b["id"] not in ids_a
        assert company_b["id"] in ids_b
        assert company_a["id"] not in ids_b

    def test_admin_sees_all_companies(
        self,
        admin_client,
        recruiter_a_client,
        recruiter_b_client,
        run_async,
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )

        list_all = run_async(admin_client.get(f"{API_V1}/companies")).json()

        ids = [c["id"] for c in list_all]
        assert company_a["id"] in ids
        assert company_b["id"] in ids

    def test_recruiter_creates_job_for_own_company(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        body = {**JOB_BODY, "company_id": company_a["id"]}

        resp = run_async(
            recruiter_a_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 201
        assert resp.json()["company_id"] == company_a["id"]

    def test_recruiter_cannot_create_job_for_other_company(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        assert company_a["id"] != company_b["id"]

        body = {**JOB_BODY, "company_id": company_b["id"]}
        resp = run_async(
            recruiter_a_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 403
        assert (
            "permission" in resp.json()["detail"].lower()
        )
        count = run_async(count_jobs_for_company(company_b["id"]))
        assert count == 0

    def test_recruiter_without_company_cannot_create_job(
        self, recruiter_client, recruiter_b_client, run_async
    ):
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        body = {**JOB_BODY, "company_id": company_b["id"]}

        resp = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 403

    def test_unknown_company_returns_404(
        self, recruiter_a_client, run_async
    ):
        body = {**JOB_BODY, "company_id": str(uuid.uuid4())}

        resp = run_async(
            recruiter_a_client.post(f"{API_V1}/jobs", json=body)
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_admin_can_create_job_for_any_company(
        self, admin_client, recruiter_b_client, run_async
    ):
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        body = {**JOB_BODY, "company_id": company_b["id"]}

        resp = run_async(admin_client.post(f"{API_V1}/jobs", json=body))

        assert resp.status_code == 201


class TestMyJobs:
    """GET /jobs/mine — recruiter job-management list with ownership isolation."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="draft"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/jobs/mine"))

        assert resp.status_code == 401

    def test_candidate_gets_403(self, candidate_client, run_async):
        resp = run_async(candidate_client.get(f"{API_V1}/jobs/mine"))

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_recruiter_without_company_gets_empty_list(
        self, recruiter_client, run_async
    ):
        resp = run_async(recruiter_client.get(f"{API_V1}/jobs/mine"))

        assert resp.status_code == 200
        assert resp.json() == []

    def test_recruiter_sees_own_jobs_but_not_other_recruiter_jobs(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        draft_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Draft Job A"
        )
        published_a = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Published Job A",
            status="published",
        )
        published_b = self.create_job(
            recruiter_b_client,
            run_async,
            company_b["id"],
            "Published Job B",
            status="published",
        )

        resp_a = run_async(recruiter_a_client.get(f"{API_V1}/jobs/mine"))
        assert resp_a.status_code == 200
        ids_a = [job["id"] for job in resp_a.json()]
        assert draft_a["id"] in ids_a
        assert published_a["id"] in ids_a
        assert published_b["id"] not in ids_a

        resp_b = run_async(recruiter_b_client.get(f"{API_V1}/jobs/mine"))
        assert resp_b.status_code == 200
        ids_b = [job["id"] for job in resp_b.json()]
        assert published_b["id"] in ids_b
        assert draft_a["id"] not in ids_b
        assert published_a["id"] not in ids_b

    def test_admin_sees_all_jobs(
        self, admin_client, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        job_b = self.create_job(
            recruiter_b_client,
            run_async,
            company_b["id"],
            "Job B",
            status="published",
        )

        resp = run_async(admin_client.get(f"{API_V1}/jobs/mine"))

        assert resp.status_code == 200
        ids = [job["id"] for job in resp.json()]
        assert job_a["id"] in ids
        assert job_b["id"] in ids

    def test_public_get_jobs_still_only_returns_published(
        self, client, run_async, recruiter_a_client
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        draft = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Draft Job"
        )
        published = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Published Job",
            status="published",
        )

        resp = run_async(client.get(f"{API_V1}/jobs"))

        assert resp.status_code == 200
        ids = [job["id"] for job in resp.json()["items"]]
        assert published["id"] in ids
        assert draft["id"] not in ids


class TestJobCompanyName:
    """company_name enrichment on all JobRead responses (OPTION A)."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_public_list_includes_company_name(
        self, client, recruiter_client, run_async
    ):
        company = self.create_company(
            recruiter_client, run_async, "acme-name", "444444444"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(client.get(f"{API_V1}/jobs"))

        assert resp.status_code == 200
        match = next(
            item for item in resp.json()["items"] if item["id"] == job["id"]
        )
        assert match["company_name"] == company["name"]
        assert match["company_id"] == company["id"]

    def test_detail_includes_company_name(
        self, client, recruiter_client, run_async
    ):
        company = self.create_company(
            recruiter_client, run_async, "acme-name", "444444444"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))

        assert resp.status_code == 200
        assert resp.json()["company_name"] == company["name"]

    def test_mine_includes_company_name(self, recruiter_client, run_async):
        company = self.create_company(
            recruiter_client, run_async, "acme-name", "444444444"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        resp = run_async(recruiter_client.get(f"{API_V1}/jobs/mine"))

        assert resp.status_code == 200
        match = next(
            item for item in resp.json() if item["id"] == job["id"]
        )
        assert match["company_name"] == company["name"]

    def test_create_response_includes_company_name(
        self, recruiter_client, run_async
    ):
        company = self.create_company(
            recruiter_client, run_async, "acme-name", "444444444"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
        }

        resp = run_async(recruiter_client.post(f"{API_V1}/jobs", json=body))

        assert resp.status_code == 201
        assert resp.json()["company_name"] == company["name"]


class TestJobSkillsRegression:
    """Regression tests for Job skills in GET /jobs/{id} endpoint."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_get_job_returns_skills(self, client, recruiter_client, run_async):
        """Test that GET /jobs/{id} returns skills array."""
        company = self.create_company(
            recruiter_client, run_async, "acme-skills", "444444444"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
            "skills": ["Python", "FastAPI", "SQL Server"],
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        # Verify skills are returned in GET /jobs/{id}
        resp = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))
        assert resp.status_code == 200
        body = resp.json()
        assert "skills" in body
        assert isinstance(body["skills"], list)
        # The job should have the skills from the request (order may vary)
        assert set(body["skills"]) == {"Python", "FastAPI", "SQL Server"}


class TestJobListSkillsRegression:
    """Regression tests for Job skills in list endpoints (GET /jobs, GET /jobs/mine).
    
    These tests verify that MissingGreenlet is not raised when serializing
    jobs with skills in list endpoints that use to_job_read().
    """

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_public_list_job_with_skills(self, client, recruiter_client, run_async):
        """PUBLIC LIST — JOB WITH SKILLS
        
        Create a published job with explicit skills, call GET /api/v1/jobs,
        assert HTTP 200 and that the returned job contains the expected skills.
        """
        company = self.create_company(
            recruiter_client, run_async, "acme-list-skills", "555555555"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        # Call the public list endpoint
        resp = run_async(client.get(f"{API_V1}/jobs"))
        assert resp.status_code == 200
        
        # Find our job in the list
        items = resp.json()["items"]
        match = next(item for item in items if item["id"] == job["id"])
        
        # Assert skills are correctly serialized
        assert "skills" in match
        assert isinstance(match["skills"], list)
        assert set(match["skills"]) == {"Python", "FastAPI", "PostgreSQL"}

    def test_public_list_job_without_skills(self, client, recruiter_client, run_async):
        """PUBLIC LIST — JOB WITHOUT SKILLS
        
        Create a published job without skills, call GET /api/v1/jobs,
        assert HTTP 200 and skills == [].
        """
        company = self.create_company(
            recruiter_client, run_async, "acme-no-skills", "666666666"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
            # No skills field - should default to empty
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        # Call the public list endpoint
        resp = run_async(client.get(f"{API_V1}/jobs"))
        assert resp.status_code == 200
        
        # Find our job in the list
        items = resp.json()["items"]
        match = next(item for item in items if item["id"] == job["id"])
        
        # Assert skills is an empty list
        assert "skills" in match
        assert match["skills"] == []

    def test_recruiter_list_job_with_skills(self, recruiter_client, run_async):
        """RECRUITER LIST — JOB WITH SKILLS
        
        Create recruiter/company/job with skills, call GET /api/v1/jobs/mine as recruiter,
        assert HTTP 200 and skills serialize correctly.
        """
        company = self.create_company(
            recruiter_client, run_async, "acme-recruiter-skills", "777777777"
        )
        body = {
            **JOB_BODY,
            "company_id": company["id"],
            "status": "published",
            "skills": ["React", "TypeScript", "Node.js"],
        }
        job = run_async(
            recruiter_client.post(f"{API_V1}/jobs", json=body)
        ).json()

        # Call the recruiter list endpoint
        resp = run_async(recruiter_client.get(f"{API_V1}/jobs/mine"))
        assert resp.status_code == 200
        
        # Find our job in the list
        items = resp.json()
        match = next(item for item in items if item["id"] == job["id"])
        
        # Assert skills are correctly serialized
        assert "skills" in match
        assert isinstance(match["skills"], list)
        assert set(match["skills"]) == {"React", "TypeScript", "Node.js"}


class TestMyJobDetail:
    """GET /jobs/mine/{id} — recruiter-scoped job detail with ownership."""

    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="draft"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(client.get(f"{API_V1}/jobs/mine/{uuid.uuid4()}"))

        assert resp.status_code == 401

    def test_candidate_gets_403(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.get(f"{API_V1}/jobs/mine/{uuid.uuid4()}")
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_recruiter_own_draft_returns_200(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        draft = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Draft Job A"
        )
        assert draft["status"] == "draft"

        resp = run_async(
            recruiter_a_client.get(f"{API_V1}/jobs/mine/{draft['id']}")
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == draft["id"]
        assert body["status"] == "draft"
        assert body["company_name"] == company_a["name"]

    def test_recruiter_own_published_returns_200(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        published = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Published Job A",
            status="published",
        )

        resp = run_async(
            recruiter_a_client.get(f"{API_V1}/jobs/mine/{published['id']}")
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    def test_recruiter_b_cannot_access_recruiter_a_job(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            recruiter_b_client.get(f"{API_V1}/jobs/mine/{job_a['id']}")
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_admin_can_access_any_job(
        self, admin_client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        draft_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Draft Job A"
        )

        resp = run_async(admin_client.get(f"{API_V1}/jobs/mine/{draft_a['id']}"))

        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    def test_public_draft_still_404(
        self, client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        draft = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Draft Job A"
        )

        resp = run_async(client.get(f"{API_V1}/jobs/{draft['id']}"))

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"

    def test_public_published_still_200(
        self, client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        published = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Published Job A",
            status="published",
        )

        resp = run_async(client.get(f"{API_V1}/jobs/{published['id']}"))

        assert resp.status_code == 200

    def test_mine_list_and_detail_isolation(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        company_b = self.create_company(
            recruiter_b_client, run_async, "acme-b", "222222222"
        )
        draft_a = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Draft Job A"
        )
        draft_b = self.create_job(
            recruiter_b_client, run_async, company_b["id"], "Draft Job B"
        )

        list_a = run_async(recruiter_a_client.get(f"{API_V1}/jobs/mine")).json()
        ids_a = [job["id"] for job in list_a]
        assert draft_a["id"] in ids_a
        assert draft_b["id"] not in ids_a

        detail_b = run_async(
            recruiter_a_client.get(f"{API_V1}/jobs/mine/{draft_b['id']}")
        )
        assert detail_b.status_code == 404


class FakeEmbeddingProvider:
    def __init__(self):
        self.last_text = None

    async def embed_text(self, text: str) -> list[float]:
        self.last_text = text
        return [0.5, 0.5, 0.5, 0.5]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]


class FakeVectorRepository:
    def __init__(self):
        self.job_vectors: dict[str, dict] = {}
        self.deleted_point_ids: list[str] = []

    async def upsert_job_vector(
        self, job_id, vector, skills=None, created_at=None, status=None
    ):
        self.job_vectors[str(job_id)] = {
            "vector": vector,
            "skills": skills or [],
            "created_at": created_at,
            "status": status,
        }

    async def delete_vector(self, collection_name, point_id):
        self.deleted_point_ids.append(str(point_id))
        self.job_vectors.pop(str(point_id), None)

    async def delete_vectors_by_filter(self, collection_name, filter_key, filter_value):
        return None


@pytest.fixture
def job_service_override():
    from app.api.deps import get_db as app_get_db
    from app.api.v1.endpoints import jobs as jobs_endpoints
    from app.services.job_service import JobService

    embedding = FakeEmbeddingProvider()
    vector_repository = FakeVectorRepository()

    async def _override(db=Depends(app_get_db)):
        return JobService(
            db,
            embedding_service=embedding,
            vector_repository=vector_repository,
        )

    app.dependency_overrides[jobs_endpoints._get_job_service] = _override
    yield vector_repository, embedding
    app.dependency_overrides.pop(jobs_endpoints._get_job_service, None)


class TestUpdateJobApi:
    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="draft"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_recruiter_updates_own_job(
        self, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Backend Engineer"
        )

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}",
                json={
                    "title": "Senior Backend Engineer",
                    "description": "Build scalable services",
                    "location": "Da Nang",
                },
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == job["id"]
        assert body["title"] == "Senior Backend Engineer"
        assert body["description"] == "Build scalable services"
        assert body["location"] == "Da Nang"
        assert body["status"] == "draft"

        detail = run_async(
            recruiter_a_client.get(f"{API_V1}/jobs/mine/{job['id']}")
        )
        assert detail.status_code == 200
        assert detail.json()["title"] == "Senior Backend Engineer"

    def test_update_reindexes_vector_with_new_content(
        self, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Old Title"
        )
        vector_repository, embedding = job_service_override

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}",
                json={"title": "Brand New Role"},
            )
        )

        assert resp.status_code == 200
        stored = vector_repository.job_vectors[str(job["id"])]
        assert stored is not None
        assert stored["vector"] == [0.5, 0.5, 0.5, 0.5]
        assert "Brand New Role" in embedding.last_text

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(client.patch(f"{API_V1}/jobs/mine/{uuid.uuid4()}", json={}))
        assert resp.status_code == 401

    def test_candidate_gets_403(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/jobs/mine/{uuid.uuid4()}", json={}
            )
        )
        assert resp.status_code == 403

    def test_recruiter_b_cannot_update_other_company_job(
        self, recruiter_a_client, recruiter_b_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}",
                json={"title": "Hijacked"},
            )
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_admin_can_update_any_job(
        self, admin_client, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            admin_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}", json={"title": "Admin Edit"}
            )
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Admin Edit"

    def test_status_field_in_update_is_ignored(
        self, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Backend Engineer"
        )

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}",
                json={"title": "New Title", "status": "closed"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    def test_empty_update_returns_unchanged_job(
        self, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Backend Engineer"
        )

        resp = run_async(
            recruiter_a_client.patch(f"{API_V1}/jobs/mine/{job['id']}", json={})
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Backend Engineer"


class TestJobStatusApi:
    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="draft"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_draft_to_published_becomes_public(
        self, client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Backend Engineer"
        )
        assert job["status"] == "draft"

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "published"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "published"
        public = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))
        assert public.status_code == 200

    def test_close_published_removes_from_public(
        self, client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Backend Engineer",
            status="published",
        )

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "closed"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"
        assert run_async(
            client.get(f"{API_V1}/jobs/{job['id']}")
        ).status_code == 404
        listing = run_async(client.get(f"{API_V1}/jobs")).json()
        assert job["id"] not in [item["id"] for item in listing["items"]]

    def test_reopen_closed_returns_to_public(
        self, client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Backend Engineer",
            status="published",
        )
        run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "closed"},
            )
        )

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "published"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "published"
        public = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))
        assert public.status_code == 200

    def test_invalid_transition_returns_400(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Backend Engineer"
        )

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "closed"},
            )
        )

        assert resp.status_code == 400
        assert "Cannot change job status" in resp.json()["detail"]

    def test_expired_cannot_transition(
        self, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Backend Engineer",
            status="expired",
        )

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "published"},
            )
        )

        assert resp.status_code == 400

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(
            client.patch(
                f"{API_V1}/jobs/mine/{uuid.uuid4()}/status",
                json={"status": "published"},
            )
        )
        assert resp.status_code == 401

    def test_candidate_gets_403(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/jobs/mine/{uuid.uuid4()}/status",
                json={"status": "published"},
            )
        )
        assert resp.status_code == 403

    def test_recruiter_b_cannot_change_other_company_job_status(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "published"},
            )
        )

        assert resp.status_code == 404

    def test_admin_can_change_status(
        self, admin_client, recruiter_a_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Backend Engineer"
        )

        resp = run_async(
            admin_client.patch(
                f"{API_V1}/jobs/mine/{job['id']}/status",
                json={"status": "published"},
            )
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "published"


class TestDeleteJobApi:
    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_job(client, run_async, company_id, title, status="draft"):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
            "status": status,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_recruiter_soft_deletes_own_job(
        self, client, recruiter_a_client, run_async, job_service_override
    ):
        vector_repository, _ = job_service_override
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Backend Engineer",
            status="published",
        )

        resp = run_async(
            recruiter_a_client.delete(f"{API_V1}/jobs/mine/{job['id']}")
        )

        assert resp.status_code == 204
        assert str(job["id"]) in vector_repository.deleted_point_ids
        assert str(job["id"]) not in vector_repository.job_vectors
        assert run_async(
            recruiter_a_client.get(f"{API_V1}/jobs/mine/{job['id']}")
        ).status_code == 404
        assert run_async(client.get(f"{API_V1}/jobs/{job['id']}")).status_code == 404
        listing = run_async(client.get(f"{API_V1}/jobs")).json()
        assert job["id"] not in [item["id"] for item in listing["items"]]
        assert run_async(count_jobs_for_company(company_a["id"])) == 1

    def test_anonymous_gets_401(self, client, run_async):
        resp = run_async(client.delete(f"{API_V1}/jobs/mine/{uuid.uuid4()}"))
        assert resp.status_code == 401

    def test_candidate_gets_403(self, candidate_client, run_async):
        resp = run_async(
            candidate_client.delete(f"{API_V1}/jobs/mine/{uuid.uuid4()}")
        )
        assert resp.status_code == 403

    def test_recruiter_b_cannot_delete_other_company_job(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(
            recruiter_b_client.delete(f"{API_V1}/jobs/mine/{job['id']}")
        )

        assert resp.status_code == 404

    def test_admin_can_delete_any_job(
        self, admin_client, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )

        resp = run_async(admin_client.delete(f"{API_V1}/jobs/mine/{job['id']}"))

        assert resp.status_code == 204

    def test_soft_delete_preserves_applications(
        self, candidate_client, recruiter_a_client, run_async, job_service_override
    ):
        company_a = self.create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = self.create_job(
            recruiter_a_client,
            run_async,
            company_a["id"],
            "Preserved Role",
            status="published",
        )
        profile = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Jane Doe", "title": "Engineer"},
            )
        )
        assert profile.status_code == 201, profile.text
        applied = apply_job_with_resume(
            candidate_client, run_async, job["id"]
        )
        assert applied.status_code == 201, applied.text

        resp = run_async(
            recruiter_a_client.delete(f"{API_V1}/jobs/mine/{job['id']}")
        )
        assert resp.status_code == 204

        history = run_async(
            candidate_client.get(f"{API_V1}/applications/mine")
        )
        assert history.status_code == 200
        assert any(
            item["job_id"] == job["id"] for item in history.json()
        )


# ============================================================================
# Wave 1.4 Phase 2: Jobs Workspace Context, Quotas & Tenant Isolation (P59-P70)
# ============================================================================

from app.domain.enums import (
    JobStatus,
    JobType,
    MembershipRole,
    WorkplaceType,
)
from app.models import (
    Job,
    RecruiterProfile,
    Subscription,
)
from tests.integration import company_billing_helpers as cbh


def test_p59_jobs_api_creation_resolves_workspace_context_and_passes_to_job_service(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            company = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await cbh._create_plan(session, max_job_posts=10)
            await cbh._create_company_subscription(
                session,
                company_id=company.id,
                user_id=user.id,
                plan_id=plan.id,
            )
            await session.commit()
            company_id = company.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(company_id)},
                json={
                    "title": "Backend Dev",
                    "description": "FastAPI Job",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "draft",
                },
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["company_id"] == str(company_id)
        finally:
            await client.aclose()

    run_async(_run())


def test_p60_creating_published_job_in_workspace_a_debits_company_a_only(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_a = await cbh._create_company(session)
            comp_b = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            await cbh._create_membership(
                session,
                company_id=comp_b.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await cbh._create_plan(session, max_job_posts=10)
            sub_a = await cbh._create_company_subscription(
                session, company_id=comp_a.id, user_id=user.id, plan_id=plan.id
            )
            sub_b = await cbh._create_company_subscription(
                session, company_id=comp_b.id, user_id=user.id, plan_id=plan.id
            )
            await session.commit()
            comp_a_id, sub_a_id, sub_b_id = comp_a.id, sub_a.id, sub_b.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(comp_a_id)},
                json={
                    "title": "Software Engineer",
                    "description": "Python developer",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "published",
                },
            )
            assert resp.status_code == 201, resp.text
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            sa = await check.get(Subscription, sub_a_id)
            sb = await check.get(Subscription, sub_b_id)
            assert sa.job_posts_used == 1
            assert sb.job_posts_used == 0

    run_async(_run())


def test_p61_updating_company_b_job_while_workspace_a_selected_returns_403(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_a = await cbh._create_company(session, name="Co A")
            comp_b = await cbh._create_company(session, name="Co B")
            await cbh._create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            await cbh._create_membership(
                session,
                company_id=comp_b.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            job_b = Job(
                company_id=comp_b.id,
                title="Job in B",
                description="Desc B",
                job_type=JobType.FULL_TIME,
                workplace_type=WorkplaceType.REMOTE,
                status=JobStatus.DRAFT,
            )
            session.add(job_b)
            await session.commit()
            comp_a_id, job_b_id = comp_a.id, job_b.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.patch(
                f"{API_V1}/jobs/mine/{job_b_id}",
                headers={"X-Company-ID": str(comp_a_id)},
                json={"title": "Hacked Title"},
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

    run_async(_run())


def test_p62_updating_job_cannot_mutate_company_id_through_request_payload(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_a = await cbh._create_company(session, name="Co A")
            comp_b = await cbh._create_company(session, name="Co B")
            await cbh._create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            job_a = Job(
                company_id=comp_a.id,
                title="Job A",
                description="Desc A",
                job_type=JobType.FULL_TIME,
                workplace_type=WorkplaceType.REMOTE,
                status=JobStatus.DRAFT,
            )
            session.add(job_a)
            await session.commit()
            comp_a_id, comp_b_id, job_a_id = comp_a.id, comp_b.id, job_a.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.patch(
                f"{API_V1}/jobs/mine/{job_a_id}",
                headers={"X-Company-ID": str(comp_a_id)},
                json={"title": "Updated A", "company_id": str(comp_b_id)},
            )
            assert resp.status_code == 200
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            j = await check.get(Job, job_a_id)
            assert j.company_id == comp_a_id

    run_async(_run())


def test_p63_multi_company_recruiter_selecting_workspace_a_cannot_debit_company_b(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_a = await cbh._create_company(session, name="Co A")
            comp_b = await cbh._create_company(session, name="Co B")
            await cbh._create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            await cbh._create_membership(
                session,
                company_id=comp_b.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await cbh._create_plan(session, max_job_posts=10)
            sub_a = await cbh._create_company_subscription(
                session, company_id=comp_a.id, user_id=user.id, plan_id=plan.id
            )
            sub_b = await cbh._create_company_subscription(
                session, company_id=comp_b.id, user_id=user.id, plan_id=plan.id
            )
            await session.commit()
            comp_a_id, comp_b_id = comp_a.id, comp_b.id
            sub_a_id, sub_b_id = sub_a.id, sub_b.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(comp_a_id)},
                json={
                    "company_id": str(comp_b_id),
                    "title": "Cross Co Post",
                    "description": "Desc",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "published",
                },
            )
            if resp.status_code == 201:
                assert resp.json()["company_id"] == str(comp_a_id)
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            sb = await check.get(Subscription, sub_b_id)
            assert sb.job_posts_used == 0

    run_async(_run())


def test_p64_legacy_recruiter_without_workspace_context_can_create_published_job_with_personal_quota(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp = await cbh._create_company(session)
            rec_profile = RecruiterProfile(
                user_id=user.id,
                company_id=comp.id,
                full_name="Legacy Recruiter",
            )
            plan = await cbh._create_plan(session, max_job_posts=5)
            sub = await cbh._create_personal_subscription(
                session, user_id=user.id, plan_id=plan.id
            )
            session.add(rec_profile)
            await session.commit()
            sub_id = sub.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                json={
                    "title": "Legacy Job",
                    "description": "Desc",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "published",
                },
            )
            assert resp.status_code == 201, resp.text
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            s = await check.get(Subscription, sub_id)
            assert s.job_posts_used == 1

    run_async(_run())


def test_p65_legacy_recruiter_without_workspace_context_can_update_eligible_legacy_job(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp = await cbh._create_company(session)
            rec_profile = RecruiterProfile(
                user_id=user.id,
                company_id=comp.id,
                full_name="Legacy Recruiter",
            )
            job = Job(
                company_id=comp.id,
                title="Legacy Job",
                description="Desc",
                job_type=JobType.FULL_TIME,
                workplace_type=WorkplaceType.REMOTE,
                status=JobStatus.DRAFT,
            )
            session.add_all([rec_profile, job])
            await session.commit()
            job_id = job.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.patch(
                f"{API_V1}/jobs/mine/{job_id}",
                json={"title": "Updated Legacy Job"},
            )
            assert resp.status_code == 200
            assert resp.json()["title"] == "Updated Legacy Job"
        finally:
            await client.aclose()

    run_async(_run())


def test_p66_company_workspace_request_with_exhausted_company_quota_fails_closed(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=comp.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            plan = await cbh._create_plan(session, max_job_posts=2)
            sub_co = await cbh._create_company_subscription(
                session,
                company_id=comp.id,
                user_id=user.id,
                plan_id=plan.id,
                max_job_posts=2,
                job_posts_used=2,
            )
            sub_personal = await cbh._create_personal_subscription(
                session,
                user_id=user.id,
                plan_id=plan.id,
                max_job_posts=5,
            )
            await session.commit()
            comp_id = comp.id
            sub_co_id = sub_co.id
            sub_pers_id = sub_personal.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                headers={"X-Company-ID": str(comp_id)},
                json={
                    "title": "Exhausted Job Post",
                    "description": "Desc",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "published",
                },
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

        async with async_session_factory() as check:
            sco = await check.get(Subscription, sub_co_id)
            spers = await check.get(Subscription, sub_pers_id)
            assert sco.job_posts_used == 2
            assert spers.job_posts_used == 0

    run_async(_run())


def test_p67_omitting_x_company_id_cannot_bypass_tenant_isolation_to_access_company_owned_job(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_a = await cbh._create_company(session, name="Tenant A")
            comp_b = await cbh._create_company(session, name="Tenant B")
            await cbh._create_membership(
                session,
                company_id=comp_a.id,
                user_id=user.id,
                role=MembershipRole.ADMIN,
            )
            job = Job(
                company_id=comp_b.id,
                title="Workspace Owned Job in Tenant B",
                description="Desc",
                job_type=JobType.FULL_TIME,
                workplace_type=WorkplaceType.REMOTE,
                status=JobStatus.DRAFT,
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.patch(
                f"{API_V1}/jobs/mine/{job_id}",
                json={"title": "Hacked Update"},
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

    run_async(_run())


def test_p68_legacy_recruiter_without_x_company_id_cannot_create_job_for_workspace_company(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            admin_user = await cbh._create_user(session)
            legacy_user = await cbh._create_user(session)
            comp = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=comp.id,
                user_id=admin_user.id,
                role=MembershipRole.ADMIN,
            )
            rec_profile = RecruiterProfile(
                user_id=legacy_user.id,
                company_id=comp.id,
                full_name="Legacy Recruiter",
            )
            session.add(rec_profile)
            await session.commit()

        client = await cbh._make_jwt_client_for_user(legacy_user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                json={
                    "title": "Bypass Post",
                    "description": "Desc",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "draft",
                },
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

    run_async(_run())


def test_p69_legacy_recruiter_without_x_company_id_cannot_update_workspace_company_job(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            admin_user = await cbh._create_user(session)
            legacy_user = await cbh._create_user(session)
            comp = await cbh._create_company(session)
            await cbh._create_membership(
                session,
                company_id=comp.id,
                user_id=admin_user.id,
                role=MembershipRole.ADMIN,
            )
            rec_profile = RecruiterProfile(
                user_id=legacy_user.id,
                company_id=comp.id,
                full_name="Legacy Recruiter",
            )
            job = Job(
                company_id=comp.id,
                title="Admin Job",
                description="Desc",
                job_type=JobType.FULL_TIME,
                workplace_type=WorkplaceType.REMOTE,
                status=JobStatus.DRAFT,
            )
            session.add_all([rec_profile, job])
            await session.commit()
            job_id = job.id

        client = await cbh._make_jwt_client_for_user(legacy_user)
        try:
            resp = await client.patch(
                f"{API_V1}/jobs/mine/{job_id}",
                json={"title": "Unauthorized Modification"},
            )
            assert resp.status_code == 403
        finally:
            await client.aclose()

    run_async(_run())


def test_p70_legacy_job_creation_derives_company_id_from_recruiter_profile(
    run_async,
):
    async def _run():
        async with async_session_factory() as session:
            user = await cbh._create_user(session)
            comp_real = await cbh._create_company(session, name="Real Legacy Co")
            comp_tamper = await cbh._create_company(session, name="Tampered Co")
            rec_profile = RecruiterProfile(
                user_id=user.id,
                company_id=comp_real.id,
                full_name="Legacy Recruiter",
            )
            session.add(rec_profile)
            await session.commit()
            comp_real_id = comp_real.id
            comp_tamper_id = comp_tamper.id

        client = await cbh._make_jwt_client_for_user(user)
        try:
            resp = await client.post(
                f"{API_V1}/jobs",
                json={
                    "company_id": str(comp_tamper_id),
                    "title": "Tampered Job",
                    "description": "Desc",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "status": "draft",
                },
            )
            assert resp.status_code == 201
            assert resp.json()["company_id"] == str(comp_real_id)
        finally:
            await client.aclose()

    run_async(_run())
