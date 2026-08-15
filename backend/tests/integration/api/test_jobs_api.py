import uuid

import pytest
from sqlalchemy import func, select

from app.database.session import async_session_factory
from app.models import Job
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
        ids = [job["id"] for job in resp.json()]
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
            item for item in resp.json() if item["id"] == job["id"]
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