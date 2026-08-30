import uuid

import pytest
from fastapi import Depends

from app.api.v1.endpoints import companies as companies_endpoints
from app.main import app
from app.services.company_service import CompanyService
from app.services.job_service import JobService
from tests.integration.api.conftest import API_V1

COMPANY_BODY = {
    "name": "Edit Corp",
    "slug": "edit-corp",
    "tax_code": "444444444",
    "size": "startup",
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


def _create_company(client, run_async, slug=None, tax_code=None):
    body = {**COMPANY_BODY}
    if slug:
        body["slug"] = slug
    if tax_code:
        body["tax_code"] = tax_code
    resp = run_async(client.post(f"{API_V1}/companies", json=body))
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestRecruiterCompanyUpdate:
    def test_anonymous_update_401(self, client, run_async):
        resp = run_async(
            client.patch(
                f"{API_V1}/companies/{uuid.uuid4()}",
                json={"name": "Renamed"},
            )
        )
        assert resp.status_code == 401

    def test_candidate_update_forbidden(
        self, candidate_client, run_async
    ):
        resp = run_async(
            candidate_client.patch(
                f"{API_V1}/companies/{uuid.uuid4()}",
                json={"name": "Renamed"},
            )
        )
        assert resp.status_code == 403

    def test_recruiter_cannot_update_foreign_company(
        self, recruiter_a_client, recruiter_b_client, run_async
    ):
        company = _create_company(recruiter_a_client, run_async)
        resp = run_async(
            recruiter_b_client.patch(
                f"{API_V1}/companies/{company['id']}",
                json={"name": "Hijacked"},
            )
        )
        assert resp.status_code == 403

        detail = run_async(
            recruiter_a_client.get(f"{API_V1}/companies/{company['id']}")
        )
        assert detail.status_code == 200
        assert detail.json()["name"] == COMPANY_BODY["name"]

    def test_recruiter_updates_own_company(
        self, recruiter_a_client, run_async
    ):
        company = _create_company(recruiter_a_client, run_async)
        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/{company['id']}",
                json={"name": "Renamed Corp", "size": "enterprise"},
            )
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Renamed Corp"
        assert data["size"] == "enterprise"
        assert data["slug"] == company["slug"]
        assert data["tax_code"] == company["tax_code"]
        assert data["id"] == company["id"]

    def test_partial_update_preserves_other_fields(
        self, recruiter_a_client, run_async
    ):
        company = _create_company(recruiter_a_client, run_async)
        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/{company['id']}",
                json={"tax_code": "111222333"},
            )
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_code"] == "111222333"
        assert data["name"] == company["name"]
        assert data["slug"] == company["slug"]
        assert data["size"] == company["size"]

    def test_duplicate_slug_returns_400(
        self, recruiter_a_client, run_async
    ):
        first = _create_company(recruiter_a_client, run_async, slug="edit-corp")
        second = _create_company(
            recruiter_a_client, run_async, slug="edit-corp-2", tax_code="555555555"
        )
        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/{second['id']}",
                json={"slug": first["slug"]},
            )
        )
        assert resp.status_code == 400

    def test_duplicate_tax_code_returns_400(
        self, recruiter_a_client, run_async
    ):
        first = _create_company(recruiter_a_client, run_async)
        second = _create_company(
            recruiter_a_client, run_async, slug="edit-corp-2", tax_code="666666666"
        )
        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/{second['id']}",
                json={"tax_code": first["tax_code"]},
            )
        )
        assert resp.status_code == 400

    def test_unknown_company_returns_404(
        self, admin_client, run_async
    ):
        resp = run_async(
            admin_client.patch(
                f"{API_V1}/companies/{uuid.uuid4()}",
                json={"name": "Renamed"},
            )
        )
        assert resp.status_code == 404

    def test_invalid_body_returns_422(self, recruiter_a_client, run_async):
        company = _create_company(recruiter_a_client, run_async)
        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/{company['id']}",
                json={"size": "not-a-size"},
            )
        )
        assert resp.status_code == 422

    def test_non_uuid_path_rejected(self, recruiter_a_client, run_async):
        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/not-a-uuid",
                json={"name": "Renamed"},
            )
        )
        assert resp.status_code == 422

    def test_deleted_company_not_editable(
        self,
        admin_client,
        recruiter_a_client,
        run_async,
        company_service_override,
    ):
        company = _create_company(recruiter_a_client, run_async)
        resp = run_async(
            admin_client.delete(f"{API_V1}/companies/{company['id']}")
        )
        assert resp.status_code == 204

        resp = run_async(
            recruiter_a_client.patch(
                f"{API_V1}/companies/{company['id']}",
                json={"name": "Should Not Persist"},
            )
        )
        assert resp.status_code == 404
