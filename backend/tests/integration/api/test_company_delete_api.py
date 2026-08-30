import uuid

import pytest
from fastapi import Depends

from app.api.v1.endpoints import companies as companies_endpoints
from app.main import app
from app.services.company_service import CompanyService
from app.services.job_service import JobService
from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Cascade Corp",
    "slug": "cascade-corp",
    "tax_code": "999999999",
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


class FakeEmbeddingProvider:
    async def embed_text(self, text: str) -> list[float]:
        return [0.5, 0.5, 0.5, 0.5]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]


class FakeVectorRepository:
    def __init__(self):
        self.job_vectors: dict[str, dict] = {}
        self.deleted_point_ids: list[str] = []

    async def upsert_job_vector(
        self, job_id, vector, skills=None, created_at=None
    ):
        self.job_vectors[str(job_id)] = {
            "vector": vector,
            "skills": skills or [],
            "created_at": created_at,
        }

    async def delete_vector(self, collection_name, point_id):
        self.deleted_point_ids.append(str(point_id))
        self.job_vectors.pop(str(point_id), None)

    async def delete_vectors_by_filter(self, collection_name, filter_key, filter_value):
        return None


@pytest.fixture
def company_service_override():
    from app.api.deps import get_db as app_get_db

    embedding = FakeEmbeddingProvider()
    vector_repository = FakeVectorRepository()

    async def _override(db=Depends(app_get_db)):
        return CompanyService(
            db,
            job_service=JobService(
                db,
                embedding_service=embedding,
                vector_repository=vector_repository,
            ),
        )

    app.dependency_overrides[companies_endpoints._get_company_service] = _override
    yield vector_repository
    app.dependency_overrides.pop(
        companies_endpoints._get_company_service, None
    )


class TestAdminCompanyDelete:
    @staticmethod
    def create_company(client, run_async, slug, tax_code):
        body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
        resp = run_async(client.post(f"{API_V1}/companies", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def create_published_job(client, run_async, company_id, title):
        body = {
            **JOB_BODY,
            "company_id": company_id,
            "title": title,
        }
        resp = run_async(client.post(f"{API_V1}/jobs", json=body))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_anonymous_delete_forbidden_401(self, client, run_async):
        resp = run_async(client.delete(f"{API_V1}/companies/{uuid.uuid4()}"))
        assert resp.status_code == 401

    def test_candidate_delete_forbidden_403(
        self, candidate_client, run_async
    ):
        resp = run_async(
            candidate_client.delete(f"{API_V1}/companies/{uuid.uuid4()}")
        )
        assert resp.status_code == 403

    def test_recruiter_delete_forbidden_403(
        self, recruiter_a_client, run_async
    ):
        resp = run_async(
            recruiter_a_client.delete(f"{API_V1}/companies/{uuid.uuid4()}")
        )
        assert resp.status_code == 403

    def test_admin_delete_unknown_company_returns_404(
        self, admin_client, run_async
    ):
        resp = run_async(
            admin_client.delete(f"{API_V1}/companies/{uuid.uuid4()}")
        )
        assert resp.status_code == 404

    def test_admin_delete_company_with_no_jobs(
        self, admin_client, recruiter_a_client, run_async, company_service_override
    ):
        company = self.create_company(
            recruiter_a_client, run_async, "empty-co", "888888888"
        )
        resp = run_async(
            admin_client.delete(f"{API_V1}/companies/{company['id']}")
        )
        assert resp.status_code == 204

        admin_list = run_async(admin_client.get(f"{API_V1}/admin/companies"))
        item = next(
            c for c in admin_list.json()["items"] if c["id"] == company["id"]
        )
        assert item["is_deleted"] is True

    def test_admin_delete_cascades_jobs_and_preserves_applications(
        self,
        admin_client,
        recruiter_a_client,
        candidate_client,
        client,
        run_async,
        company_service_override,
    ):
        vector_repository = company_service_override
        company = self.create_company(
            recruiter_a_client, run_async, "cascade-co", "777777777"
        )
        job = self.create_published_job(
            recruiter_a_client, run_async, company["id"], "Cascade Engineer"
        )

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
        )
        assert application.status_code == 201, application.text

        resp = run_async(
            admin_client.delete(f"{API_V1}/companies/{company['id']}")
        )
        assert resp.status_code == 204

        public_company = run_async(
            client.get(f"{API_V1}/companies/{company['id']}")
        )
        assert public_company.status_code == 404

        public_job = run_async(client.get(f"{API_V1}/jobs/{job['id']}"))
        assert public_job.status_code == 404

        recruiter_job = run_async(
            recruiter_a_client.get(f"{API_V1}/jobs/mine/{job['id']}")
        )
        assert recruiter_job.status_code == 404

        listing = run_async(client.get(f"{API_V1}/jobs"))
        assert all(item["id"] != job["id"] for item in listing.json())

        assert str(job["id"]) in vector_repository.deleted_point_ids
        assert str(job["id"]) not in vector_repository.job_vectors

        mine = run_async(candidate_client.get(f"{API_V1}/applications/mine"))
        assert mine.status_code == 200
        app_id = application.json()["id"]
        assert any(item["id"] == app_id for item in mine.json())

        reapplying = run_async(
            candidate_client.post(
                f"{API_V1}/applications", json={"job_id": job["id"]}
            )
        )
        assert reapplying.status_code == 404

        admin_list = run_async(admin_client.get(f"{API_V1}/admin/companies"))
        assert admin_list.status_code == 200
        body = admin_list.json()
        item = next(
            c for c in body["items"] if c["id"] == company["id"]
        )
        assert item["is_deleted"] is True

    def test_admin_delete_is_idempotent_404_on_second_call(
        self, admin_client, recruiter_a_client, run_async, company_service_override
    ):
        company = self.create_company(
            recruiter_a_client, run_async, "twice-co", "666666666"
        )
        first = run_async(
            admin_client.delete(f"{API_V1}/companies/{company['id']}")
        )
        assert first.status_code == 204

        second = run_async(
            admin_client.delete(f"{API_V1}/companies/{company['id']}")
        )
        assert second.status_code == 404

    def test_admin_company_search_finds_locked_company(
        self,
        admin_client,
        recruiter_a_client,
        run_async,
        company_service_override,
    ):
        company = self.create_company(
            recruiter_a_client, run_async, "search-co", "555555555"
        )
        run_async(admin_client.delete(f"{API_V1}/companies/{company['id']}"))

        resp = run_async(
            admin_client.get(
                f"{API_V1}/admin/companies", params={"search": "search-co"}
            )
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(c["id"] == company["id"] for c in items)