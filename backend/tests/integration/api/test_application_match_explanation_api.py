import json
import uuid

import pytest

from tests.integration.api.conftest import API_V1

from app.api.v1.endpoints.applications import (
    _get_ai_matching_service,
    _get_match_explanation_service,
)
from app.database.session import async_session_factory
from app.main import app
from app.models import Resume
from app.services.ai_matching_service import AIMatchingService
from app.services.match_explanation_service import MatchExplanationService

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
    "experiences": [
        {
            "company": "Globex",
            "position": "Backend Engineer",
            "start_date": "2018",
            "end_date": "2021",
            "description": "Built Python microservices.",
            "skills_used": ["Python", "FastAPI"],
        }
    ],
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
    async def embed_resume(self, parsed_resume):
        return [0.5, 0.5, 0.5, 0.5]

    async def embed_job(self, parsed_job):
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
    # Deterministic explanation only: never call a real LLM provider in tests.
    app.dependency_overrides[_get_match_explanation_service] = (
        lambda: MatchExplanationService()
    )
    yield service
    app.dependency_overrides.pop(_get_ai_matching_service, None)
    app.dependency_overrides.pop(_get_match_explanation_service, None)


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

    from app.models import Job, JobSkill, Skill

    async with async_session_factory() as session:
        stmt = (
            select(Job)
            .options(selectinload(Job.job_skills).selectinload(JobSkill.skill))
            .where(Job.id == job_id)
        )
        job = (await session.execute(stmt)).scalar_one()

        for name in skill_names:
            stmt = select(Skill).where(
                Skill.name == name, Skill.is_deleted == False
            )
            skill = (await session.execute(stmt)).scalar_one_or_none()
            if skill is None:
                skill = Skill(name=name)
                session.add(skill)
                await session.flush()

            existing_association = any(
                js.skill_id == skill.id for js in job.job_skills
            )
            if not existing_association:
                session.add(
                    JobSkill(
                        job_id=job_id, skill_id=skill.id, is_mandatory=True
                    )
                )
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


def _setup_application(recruiter_client, candidate_client, run_async, slug, tax):
    company = create_company(recruiter_client, run_async, slug, tax)
    job = create_job(recruiter_client, run_async, company["id"], "Job A")
    profile = create_candidate_profile(candidate_client, run_async).json()
    application = create_application(candidate_client, run_async, job["id"])
    run_async(_seed_resume(profile["id"], PARSED_RESUME))
    run_async(_seed_job_skills(job["id"], ["Python", "Docker"]))
    return application


class TestApplicationMatchExplanation:
    def test_anonymous_returns_401(self, client, run_async, fake_ai_service):
        resp = run_async(
            client.get(
                f"{API_V1}/applications/{uuid.uuid4()}/match-explanation"
            )
        )

        assert resp.status_code == 401

    def test_candidate_returns_403(
        self, candidate_client, run_async, fake_ai_service
    ):
        resp = run_async(
            candidate_client.get(
                f"{API_V1}/applications/{uuid.uuid4()}/match-explanation"
            )
        )

        assert resp.status_code == 403

    def test_recruiter_gets_explanation(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        application = _setup_application(
            recruiter_a_client, candidate_client, run_async, "acme-a", "111111111"
        )

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
            )
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["application_id"] == application["id"]
        assert body["overall_score"] >= 0.0
        assert body["cache_state"] == "not_cached"
        assert body["confidence"] is None
        by_name = {e["skill_name"]: e for e in body["skill_evaluations"]}
        assert by_name["Python"]["status"] == "matched_evidenced"
        assert by_name["Docker"]["status"] == "not_evidenced_in_cv"

    def test_explanation_score_matches_match_endpoint(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        application = _setup_application(
            recruiter_a_client, candidate_client, run_async, "acme-a", "111111111"
        )

        match = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match"
            )
        )
        explanation = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
            )
        )

        assert match.status_code == 200
        assert explanation.status_code == 200
        assert (
            explanation.json()["overall_score"]
            == match.json()["overall_score"]
        )

    def test_every_evidence_quote_is_verbatim_resume_text(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        application = _setup_application(
            recruiter_a_client, candidate_client, run_async, "acme-a", "111111111"
        )

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
            )
        )

        body = resp.json()
        resume_blob = json.dumps(PARSED_RESUME).lower()
        assert body["evidence"]
        for evidence in body["evidence"]:
            assert evidence["quote"].lower() in resume_blob

    def test_foreign_recruiter_gets_404(
        self,
        recruiter_a_client,
        recruiter_b_client,
        candidate_client,
        run_async,
        fake_ai_service,
    ):
        application = _setup_application(
            recruiter_a_client, candidate_client, run_async, "acme-a", "111111111"
        )

        resp = run_async(
            recruiter_b_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
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
                f"{API_V1}/applications/{uuid.uuid4()}/match-explanation"
            )
        )

        assert resp.status_code == 404

    def test_no_resume_degrades_to_insufficient_data(
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

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
            )
        )

        assert resp.status_code == 200
        body = resp.json()
        assert all(
            e["status"] == "insufficient_data"
            for e in body["skill_evaluations"]
        )
        assert body["data_limitations"]

    def test_admin_gets_any_application_explanation(
        self,
        admin_client,
        recruiter_a_client,
        candidate_client,
        run_async,
        fake_ai_service,
    ):
        application = _setup_application(
            recruiter_a_client, candidate_client, run_async, "acme-a", "111111111"
        )

        resp = run_async(
            admin_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
            )
        )

        assert resp.status_code == 200

    def test_explanation_does_not_mutate_application_status(
        self, recruiter_a_client, candidate_client, run_async, fake_ai_service
    ):
        application = _setup_application(
            recruiter_a_client, candidate_client, run_async, "acme-a", "111111111"
        )

        resp = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}/match-explanation"
            )
        )
        assert resp.status_code == 200

        detail = run_async(
            recruiter_a_client.get(
                f"{API_V1}/applications/{application['id']}"
            )
        )
        assert detail.json()["status"] == "applied"
