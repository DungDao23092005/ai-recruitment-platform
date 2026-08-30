import uuid

import pytest

from tests.integration.api.conftest import API_V1, PASSWORD

from app.api.v1.endpoints.applications import _get_ai_matching_service
from app.database.session import async_session_factory
from app.main import app
from app.models import Resume, Skill
from app.services.ai_matching_service import AIMatchingService

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

PARSED_RESUME = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "0901234567",
    "title": "Senior Engineer",
    "summary": "8 years building backend systems.",
    "total_years_experience": 8.0,
    "skills": ["Python", "FastAPI", "SQL"],
    "experiences": [],
    "education": [],
    "certifications": [],
    "languages": [],
}


class FakeVectorRepository:
    def __init__(self):
        self.vectors: dict[tuple[str, str], list[float]] = {}
        self.fail = False

    async def retrieve_vector(self, collection_name, point_id):
        if self.fail:
            from app.core.exceptions import AIError

            raise AIError("Qdrant unavailable")
        return self.vectors.get((collection_name, str(point_id)))

    async def search_similar(self, *args, **kwargs):
        return []

    async def upsert_vector(self, *args, **kwargs):
        return None

    async def delete_vector(self, *args, **kwargs):
        return None

    async def delete_vectors_by_filter(self, collection_name, filter_key, filter_value):
        return None


class FakeEmbeddingService:
    def __init__(self):
        self.resume_embeds = []
        self.job_embeds = []

    def embed_resume(self, parsed_resume):
        self.resume_embeds.append(parsed_resume)
        return [0.5, 0.5, 0.5, 0.5]

    def embed_job(self, parsed_job):
        self.job_embeds.append(parsed_job)
        return [0.5, 0.5, 0.5, 0.5]


@pytest.fixture
def fake_ai_service():
    from app.ai.matching.matching_engine import MatchingEngine

    service = AIMatchingService(
        vector_repository=FakeVectorRepository(),
        embedding_service=FakeEmbeddingService(),
        matching_engine=MatchingEngine(),
    )
    app.dependency_overrides[_get_ai_matching_service] = lambda: service
    yield service
    app.dependency_overrides.pop(_get_ai_matching_service, None)


async def _seed_resume(candidate_id, parsed_data: dict | None):
    async with async_session_factory() as session:
        resume = Resume(
            candidate_id=candidate_id,
            title="cv.pdf",
            is_primary=True,
            parsed_data=parsed_data,
        )
        session.add(resume)
        await session.commit()
        return resume.id


async def _seed_job_skills(job_id, skill_names):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Job

    async with async_session_factory() as session:
        stmt = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(Job.id == job_id)
        )
        job = (await session.execute(stmt)).scalar_one()
        for name in skill_names:
            skill = Skill(name=name)
            session.add(skill)
            await session.flush()
            job.skills.append(skill)
        await session.commit()


def create_candidate_profile(candidate_client, run_async):
    return run_async(
        candidate_client.post(
            f"{API_V1}/users/me/candidate-profile",
            json={"full_name": "Jane Doe", "title": "Engineer"},
        )
    )


def create_company(client, run_async, slug, tax_code):
    body = {**COMPANY_BODY, "slug": slug, "tax_code": tax_code}
    resp = run_async(client.post(f"{API_V1}/companies", json=body))
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_job(client, run_async, company_id, title, status="published"):
    body = {
        **JOB_BODY,
        "company_id": company_id,
        "title": title,
        "status": status,
    }
    resp = run_async(client.post(f"{API_V1}/jobs", json=body))
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_application(candidate_client, run_async, job_id):
    resp = run_async(
        candidate_client.post(
            f"{API_V1}/applications", json={"job_id": job_id}
        )
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestGetApplicationMatch:
    """GET /applications/{id}/match — deterministic AI match for an application."""

    def test_anonymous_returns_401(self, client, run_async, fake_ai_service):
        resp = run_async(
            client.get(f"{API_V1}/applications/{uuid.uuid4()}/match")
        )

        assert resp.status_code == 401

    def test_candidate_returns_403(
        self, candidate_client, run_async, fake_ai_service
    ):
        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/{uuid.uuid4()}/match"
            )
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not enough permissions"

    def test_recruiter_gets_own_application_match(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = create_application(
            candidate_client, run_async, job["id"]
        )
        run_async(_seed_resume(profile["id"], PARSED_RESUME))
        run_async(_seed_job_skills(job["id"], ["Python", "Docker"]))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert 0.0 <= body["overall_score"] <= 100.0
        assert set(body.keys()) == {
            "overall_score",
            "cosine_similarity",
            "skill_coverage_score",
            "experience_match_score",
            "matching_skills",
            "skill_gap",
            "match_reasons",
        }
        assert "Python" in body["matching_skills"]
        assert "Docker" in body["skill_gap"]

    def test_match_uses_candidate_resume_not_other_candidates(
        self, recruiter_a_client, candidate_client, candidate_b_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile_a = create_candidate_profile(candidate_client, run_async).json()
        profile_b = create_candidate_profile(candidate_b_client, run_async).json()
        run_async(
            _seed_resume(
                profile_a["id"], {**PARSED_RESUME, "skills": ["Python"]}
            )
        )
        run_async(
            _seed_resume(
                profile_b["id"], {**PARSED_RESUME, "skills": ["Go"]}
            )
        )
        run_async(_seed_job_skills(job["id"], ["Python", "Docker"]))
        app_a = create_application(candidate_client, run_async, job["id"])
        app_b = create_application(candidate_b_client, run_async, job["id"])

        resp_a = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{app_a['id']}/match"
            )
        )
        resp_b = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{app_b['id']}/match"
            )
        )

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert "Python" in resp_a.json()["matching_skills"]
        assert "Python" not in resp_b.json()["matching_skills"]
        assert "Go" not in resp_b.json()["matching_skills"]

    def test_no_resume_returns_graceful_match(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = create_application(candidate_client, run_async, job["id"])

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["matching_skills"] == []
        assert body["overall_score"] >= 0.0

    def test_resume_with_null_parsed_data_returns_graceful_match(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = create_application(candidate_client, run_async, job["id"])
        run_async(_seed_resume(profile["id"], None))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 200
        assert resp.json()["matching_skills"] == []

    def test_malformed_parsed_data_returns_graceful_match(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = create_application(candidate_client, run_async, job["id"])
        run_async(_seed_resume(profile["id"], {"skills": "not-a-list"}))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 200
        assert resp.json()["matching_skills"] == []

    def test_qdrant_failure_returns_502_controlled(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = create_application(candidate_client, run_async, job["id"])
        run_async(_seed_resume(profile["id"], PARSED_RESUME))
        fake_ai_service.vector_repository.fail = True

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 502
        assert "AI Match unavailable" in resp.json()["detail"]
        assert "Qdrant" not in resp.json()["detail"]

    def test_foreign_recruiter_gets_404(
        self,
        recruiter_a_client,
        recruiter_b_client,
        candidate_client,
        run_async,
        fake_ai_service,
    ):
        company_a = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job_a = create_job(
            recruiter_a_client, run_async, company_a["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = create_application(candidate_client, run_async, job_a["id"])

        resp = run_async(
            recruiter_b_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Application {application['id']} not found"
        )

    def test_nonexistent_application_returns_404(
        self, recruiter_a_client, run_async, fake_ai_service
    ):
        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{uuid.uuid4()}/match"
            )
        )

        assert resp.status_code == 404
        import re

        assert (
            re.match(r"^Application [0-9a-fA-F-]{36} not found$", resp.json()["detail"])
            is not None
        )

    def test_admin_gets_any_application_match(
        self,
        admin_client,
        recruiter_a_client,
        candidate_client,
        run_async,
        fake_ai_service,
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = create_application(candidate_client, run_async, job["id"])

        resp = run_async(
            admin_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )

        assert resp.status_code == 200
        assert resp.json()["overall_score"] >= 0.0

    def test_match_does_not_mutate_application_status(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        profile = create_candidate_profile(candidate_client, run_async).json()
        application = create_application(candidate_client, run_async, job["id"])
        run_async(_seed_resume(profile["id"], PARSED_RESUME))

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )
        assert resp.status_code == 200

        detail = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "applied"

    def test_detail_includes_parsed_job_for_grounded_explanation(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        company = create_company(
            recruiter_a_client, run_async, "acme-a", "111111111"
        )
        job = create_job(
            recruiter_a_client, run_async, company["id"], "Job A"
        )
        create_candidate_profile(candidate_client, run_async)
        application = create_application(candidate_client, run_async, job["id"])
        run_async(_seed_job_skills(job["id"], ["Python"]))

        detail = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )

        assert detail.status_code == 200
        parsed_job = detail.json()["parsed_job"]
        assert parsed_job is not None
        assert parsed_job["title"] == "Job A"
        assert "Python" in parsed_job["required_skills"]