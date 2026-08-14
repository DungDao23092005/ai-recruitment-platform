from __future__ import annotations

import uuid

import pytest

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.core.config import settings
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService

from .conftest import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    QDRANT_AVAILABLE,
    SKIP_REASON_QDRANT,
    VECTOR_DIM,
)

pytestmark = pytest.mark.skipif(
    not QDRANT_AVAILABLE,
    reason=SKIP_REASON_QDRANT,
)

API_V1 = settings.API_V1_STR

MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n"
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
    b"endobj\n"
    b"4 0 obj\n<< /Length 100 >>\nstream\n"
    b"BT\n/F1 12 Tf\n72 720 Td\n"
    b"(John Doe - Senior Python Developer) Tj\n"
    b"0 -14 Td\n(Skills: Python, FastAPI) Tj\n"
    b"ET\nendstream\nendobj\n"
    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n%%EOF\n"
)

EXPECTED_RESUME = ParsedResumeSchema(
    full_name="John Doe",
    title="Senior Python Developer",
    summary="Experienced Python developer with FastAPI and SQL Server.",
    total_years_experience=5.0,
    skills=["Python", "FastAPI", "SQL Server"],
)

EXPECTED_JOB = ParsedJobSchema(
    title="Senior Python Developer",
    summary="Backend role focused on Python and FastAPI.",
    required_skills=["Python", "FastAPI", "Docker"],
    preferred_skills=["GraphQL"],
    minimum_years_experience=3.0,
)


def _make_service(vector_repository) -> AIMatchingService:
    llm = FakeLLMProvider(
        resume=EXPECTED_RESUME,
        job=EXPECTED_JOB,
    )
    return AIMatchingService(
        resume_parser=ResumeParser(llm_provider=llm),
        job_parser=JobParser(llm_provider=llm),
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        vector_repository=vector_repository,
        matching_engine=MatchingEngine(),
    )


async def _seed_job_vectors(vector_repository, skills_list) -> list[uuid.UUID]:
    job_ids = [uuid.uuid4() for _ in skills_list]
    for job_id, skills in zip(job_ids, skills_list):
        vector = FakeEmbeddingProvider._hash_vector(" ".join(skills))
        await vector_repository.upsert_job_vector(
            job_id=job_id, vector=vector, skills=skills
        )
    return job_ids


async def _seed_candidate_vectors(
    vector_repository, skills_list
) -> list[uuid.UUID]:
    candidate_ids = [uuid.uuid4() for _ in skills_list]
    for candidate_id, skills in zip(candidate_ids, skills_list):
        vector = FakeEmbeddingProvider._hash_vector(" ".join(skills))
        await vector_repository.upsert_resume_vector(
            candidate_id=candidate_id, vector=vector, skills=skills
        )
    return candidate_ids


class TestResumeIndexFlow:
    async def test_full_resume_index_and_retrieve_flow(
        self, vector_repository, tracked
    ):
        await vector_repository.init_collections()
        candidate_id = uuid.uuid4()
        tracked("resumes", candidate_id)
        service = _make_service(vector_repository)

        result = await service.process_and_index_resume(
            candidate_id=candidate_id,
            pdf_source=MINIMAL_PDF_BYTES,
        )

        assert result == EXPECTED_RESUME

        retrieved = await vector_repository.retrieve_vector(
            "resumes", candidate_id
        )
        assert retrieved is not None
        assert len(retrieved["vector"]) == VECTOR_DIM
        assert retrieved["payload"]["candidate_id"] == str(candidate_id)
        assert retrieved["payload"]["skills"] == result.skills


class TestJobIndexFlow:
    async def test_full_job_index_and_retrieve_flow(
        self, vector_repository, tracked
    ):
        await vector_repository.init_collections()
        job_id = uuid.uuid4()
        tracked("jobs", job_id)
        service = _make_service(vector_repository)

        result = await service.process_and_index_job(
            job_id=job_id,
            job_title="Senior Python Developer",
            job_description=(
                "We are hiring a Senior Python Developer with FastAPI and "
                "SQL Server experience. 3+ years required."
            ),
        )

        assert result == EXPECTED_JOB

        retrieved = await vector_repository.retrieve_vector("jobs", job_id)
        assert retrieved is not None
        assert len(retrieved["vector"]) == VECTOR_DIM
        assert retrieved["payload"]["job_id"] == str(job_id)
        assert "Python" in retrieved["payload"]["skills"]


class TestRecommendJobsRealQdrant:
    async def test_recommend_jobs_for_candidate_with_real_qdrant(
        self, vector_repository, tracked
    ):
        await vector_repository.init_collections()
        service = _make_service(vector_repository)

        candidate_id = uuid.uuid4()
        tracked("resumes", candidate_id)
        await vector_repository.upsert_resume_vector(
            candidate_id=candidate_id,
            vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
            skills=["Python", "FastAPI"],
        )

        job_ids = await _seed_job_vectors(
            vector_repository,
            [
                ["Python", "FastAPI"],
                ["Java", "Spring"],
                ["Python", "Docker"],
            ],
        )
        for job_id in job_ids:
            tracked("jobs", job_id)

        recommendations = await service.recommend_jobs_for_candidate(
            candidate_id=candidate_id,
            limit=10,
        )

        assert recommendations, "recommendations should be returned"
        scores = [rec.match_result.overall_score for rec in recommendations]
        assert scores == sorted(scores, reverse=True), (
            "ranking must be descending"
        )

        first = await service.recommend_jobs_for_candidate(
            candidate_id=candidate_id,
            limit=10,
        )
        assert [r.match_result.overall_score for r in first] == scores


class TestRecommendCandidatesRealQdrant:
    async def test_recommend_candidates_for_job_with_real_qdrant(
        self, vector_repository, tracked
    ):
        await vector_repository.init_collections()
        service = _make_service(vector_repository)

        job_id = uuid.uuid4()
        tracked("jobs", job_id)
        await vector_repository.upsert_job_vector(
            job_id=job_id,
            vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
            skills=["Python", "FastAPI"],
        )

        candidate_ids = await _seed_candidate_vectors(
            vector_repository,
            [
                ["Python", "FastAPI"],
                ["Java", "Spring"],
                ["Python"],
            ],
        )
        for candidate_id in candidate_ids:
            tracked("resumes", candidate_id)

        recommendations = await service.recommend_candidates_for_job(
            job_id=job_id,
            limit=10,
        )

        assert recommendations, "recommendations should be returned"
        scores = [rec.match_result.overall_score for rec in recommendations]
        assert scores == sorted(scores, reverse=True)


class TestRecommendationsApi:
    async def test_recommend_jobs_endpoint_with_real_qdrant(
        self,
        candidate_client,
        vector_repository,
        tracked,
        run_async,
    ):
        await vector_repository.init_collections()

        profile = run_async(
            candidate_client.post(
                f"{API_V1}/users/me/candidate-profile",
                json={"full_name": "Jane Doe", "title": "Engineer"},
            )
        )
        assert profile.status_code == 201, profile.text
        candidate_id = uuid.UUID(profile.json()["id"])
        tracked("resumes", candidate_id)

        await vector_repository.upsert_resume_vector(
            candidate_id=candidate_id,
            vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
            skills=["Python", "FastAPI"],
        )
        job_ids = await _seed_job_vectors(
            vector_repository,
            [["Python", "FastAPI"], ["Java", "Spring"]],
        )
        for job_id in job_ids:
            tracked("jobs", job_id)

        resp = run_async(
            candidate_client.get(f"{API_V1}/ai/recommendations/jobs")
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        scores = [item["match_result"]["overall_score"] for item in body]
        assert scores == sorted(scores, reverse=True)

    async def test_recommend_candidates_endpoint_with_real_qdrant(
        self,
        recruiter_client,
        vector_repository,
        tracked,
        run_async,
    ):
        await vector_repository.init_collections()

        job_id = uuid.uuid4()
        tracked("jobs", job_id)
        await vector_repository.upsert_job_vector(
            job_id=job_id,
            vector=FakeEmbeddingProvider._hash_vector("Python FastAPI"),
            skills=["Python", "FastAPI"],
        )
        candidate_ids = await _seed_candidate_vectors(
            vector_repository,
            [["Python", "FastAPI"], ["Java", "Spring"]],
        )
        for candidate_id in candidate_ids:
            tracked("resumes", candidate_id)

        resp = run_async(
            recruiter_client.get(
                f"{API_V1}/ai/recommendations/candidates",
                params={"job_id": str(job_id)},
            )
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        scores = [item["match_result"]["overall_score"] for item in body]
        assert scores == sorted(scores, reverse=True)