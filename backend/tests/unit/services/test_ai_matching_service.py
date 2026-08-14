from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.core.exceptions import EmptyDocumentError, EntityNotFoundException
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService


@pytest.fixture
def mock_dependencies():
    return {
        "resume_parser": AsyncMock(spec=ResumeParser),
        "job_parser": AsyncMock(spec=JobParser),
        "embedding_service": MagicMock(spec=EmbeddingService),
        "vector_repository": AsyncMock(spec=BaseVectorRepository),
        "matching_engine": MagicMock(spec=MatchingEngine),
    }


@pytest.fixture
def ai_service(mock_dependencies):
    return AIMatchingService(
        resume_parser=mock_dependencies["resume_parser"],
        job_parser=mock_dependencies["job_parser"],
        embedding_service=mock_dependencies["embedding_service"],
        vector_repository=mock_dependencies["vector_repository"],
        matching_engine=mock_dependencies["matching_engine"],
    )


@pytest.mark.asyncio
async def test_process_and_index_resume_success(ai_service, mock_dependencies):
    cand_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(
        full_name="John Doe",
        skills=["Python", "FastAPI"],
    )
    mock_dependencies["resume_parser"].parse.return_value = parsed_resume
    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384

    fake_pdf = b"%PDF-1.7 Fake PDF content for resume testing"

    with patch(
        "app.ai.extractors.pdf_extractor.PDFTextExtractor.extract",
        return_value="Extracted CV Text",
    ):
        result = await ai_service.process_and_index_resume(cand_id, fake_pdf)

    assert result == parsed_resume
    mock_dependencies["resume_parser"].parse.assert_awaited_once_with(
        "Extracted CV Text"
    )
    mock_dependencies["vector_repository"].upsert_vector.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_and_index_job_success(ai_service, mock_dependencies):
    job_id = uuid.uuid4()
    parsed_job = ParsedJobSchema(
        title="Senior Python Developer",
        required_skills=["Python", "SQL Server"],
        preferred_skills=["Docker"],
    )
    mock_dependencies["job_parser"].parse.return_value = parsed_job
    mock_dependencies["embedding_service"].embed_job.return_value = [0.2] * 384

    result = await ai_service.process_and_index_job(
        job_id=job_id,
        job_title="Senior Python Developer",
        job_description="We are hiring a Senior Python Developer with SQL Server experience.",
    )

    assert result == parsed_job
    mock_dependencies["job_parser"].parse.assert_awaited_once()
    mock_dependencies["vector_repository"].upsert_vector.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_and_index_job_empty_description_raises_error(
    ai_service,
):
    job_id = uuid.uuid4()
    with pytest.raises(EmptyDocumentError, match="cannot be empty"):
        await ai_service.process_and_index_job(
            job_id=job_id, job_title="Dev", job_description="   "
        )


def test_match_candidate_with_job_success(ai_service, mock_dependencies):
    parsed_resume = ParsedResumeSchema(skills=["Python"])
    parsed_job = ParsedJobSchema(required_skills=["Python"])
    expected_match = MatchResultSchema(
        overall_score=95.0,
        cosine_similarity=0.9,
        skill_coverage_score=1.0,
        experience_match_score=1.0,
        matching_skills=["Python"],
    )

    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    mock_dependencies["embedding_service"].embed_job.return_value = [0.1] * 384
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        expected_match
    )

    res = ai_service.match_candidate_with_job(parsed_resume, parsed_job)

    assert res.overall_score == 95.0
    mock_dependencies["matching_engine"].match_resume_to_job.assert_called_once()


@pytest.mark.asyncio
async def test_recommend_jobs_for_candidate_memory_data(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(skills=["Python"])

    job1_id = uuid.uuid4()
    parsed_job1 = ParsedJobSchema(title="Job 1", required_skills=["Python"])

    job2_id = uuid.uuid4()
    parsed_job2 = ParsedJobSchema(title="Job 2", required_skills=["Java"])

    match1 = MatchResultSchema(
        overall_score=90.0,
        cosine_similarity=0.9,
        skill_coverage_score=1.0,
        experience_match_score=1.0,
    )
    match2 = MatchResultSchema(
        overall_score=40.0,
        cosine_similarity=0.4,
        skill_coverage_score=0.0,
        experience_match_score=0.5,
    )

    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    mock_dependencies["embedding_service"].embed_job.return_value = [0.1] * 384
    mock_dependencies[
        "matching_engine"
    ].match_resume_to_job.side_effect = [match1, match2]

    jobs_data = [
        (job1_id, parsed_job1, None),
        (job2_id, parsed_job2, None),
    ]

    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        parsed_resume=parsed_resume,
        jobs_data=jobs_data,
        limit=10,
    )

    assert len(recs) == 2
    assert recs[0].job_id == job1_id
    assert recs[0].match_result.overall_score == 90.0
    assert recs[1].job_id == job2_id
    assert recs[1].match_result.overall_score == 40.0


@pytest.mark.asyncio
async def test_recommend_candidates_for_job_memory_data(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    parsed_job = ParsedJobSchema(title="Dev", required_skills=["FastAPI"])

    cand1_id = uuid.uuid4()
    parsed_resume1 = ParsedResumeSchema(full_name="Alice", skills=["FastAPI"])

    match1 = MatchResultSchema(
        overall_score=92.0,
        cosine_similarity=0.9,
        skill_coverage_score=1.0,
        experience_match_score=1.0,
    )

    mock_dependencies["embedding_service"].embed_job.return_value = [0.1] * 384
    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        match1
    )

    candidates_data = [(cand1_id, parsed_resume1, None)]

    recs = await ai_service.recommend_candidates_for_job(
        job_id=job_id,
        parsed_job=parsed_job,
        candidates_data=candidates_data,
        limit=5,
    )

    assert len(recs) == 1
    assert recs[0].candidate_id == cand1_id
    assert recs[0].match_result.overall_score == 92.0


@pytest.mark.asyncio
async def test_recommend_jobs_qdrant_vector_repository_fallback(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(skills=["Python"])
    target_job_id = uuid.uuid4()

    qdrant_search_return = [
        {
            "id": str(target_job_id),
            "score": 0.88,
            "payload": {
                "job_id": str(target_job_id),
                "skills": ["Python"],
                "is_deleted": False,
            },
            "vector": [0.1] * 384,
        }
    ]

    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    mock_dependencies["vector_repository"].search_similar.return_value = (
        qdrant_search_return
    )

    match_res = MatchResultSchema(
        overall_score=88.0,
        cosine_similarity=0.88,
        skill_coverage_score=1.0,
        experience_match_score=0.5,
    )
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        match_res
    )

    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        parsed_resume=parsed_resume,
        limit=5,
    )

    assert len(recs) == 1
    assert recs[0].job_id == target_job_id
    assert recs[0].match_result.overall_score == 88.0
    mock_dependencies[
        "vector_repository"
    ].search_similar.assert_awaited_once_with(
        collection_name="jobs", query_vector=[0.1] * 384, limit=5
    )


@pytest.mark.asyncio
async def test_recommend_jobs_calls_retrieve_vector_when_no_vector(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    target_job_id = uuid.uuid4()

    retrieved = {
        "id": str(cand_id),
        "vector": [0.3] * 384,
        "payload": {"candidate_id": str(cand_id), "skills": ["Python"]},
    }
    mock_dependencies["vector_repository"].retrieve_vector.return_value = (
        retrieved
    )
    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_job_id),
            "score": 0.8,
            "payload": {"skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    match_res = MatchResultSchema(
        overall_score=80.0,
        cosine_similarity=0.8,
        skill_coverage_score=1.0,
        experience_match_score=0.5,
    )
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        match_res
    )

    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        limit=5,
    )

    mock_dependencies[
        "vector_repository"
    ].retrieve_vector.assert_awaited_once_with(
        collection_name="resumes", point_id=cand_id
    )
    assert len(recs) == 1
    assert recs[0].job_id == target_job_id


@pytest.mark.asyncio
async def test_recommend_jobs_retrieve_missing_raises_not_found(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    mock_dependencies["vector_repository"].retrieve_vector.return_value = None

    with pytest.raises(EntityNotFoundException):
        await ai_service.recommend_jobs_for_candidate(
            candidate_id=cand_id, limit=5
        )


@pytest.mark.asyncio
async def test_recommend_jobs_explicit_vector_skips_retrieve(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    target_job_id = uuid.uuid4()

    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_job_id),
            "score": 0.9,
            "payload": {"skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    match_res = MatchResultSchema(
        overall_score=90.0,
        cosine_similarity=0.9,
        skill_coverage_score=1.0,
        experience_match_score=1.0,
    )
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        match_res
    )

    await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        candidate_vector=[0.7] * 384,
        limit=5,
    )

    mock_dependencies["vector_repository"].retrieve_vector.assert_not_awaited()
    mock_dependencies[
        "vector_repository"
    ].search_similar.assert_awaited_once_with(
        collection_name="jobs",
        query_vector=[0.7] * 384,
        limit=5,
    )


@pytest.mark.asyncio
async def test_recommend_jobs_explicit_parsed_resume_embeds_not_retrieves(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    target_job_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(skills=["Python"])

    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.4
    ] * 384
    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_job_id),
            "score": 0.75,
            "payload": {"skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        MatchResultSchema(
            overall_score=75.0,
            cosine_similarity=0.75,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
        )
    )

    await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        parsed_resume=parsed_resume,
        limit=5,
    )

    mock_dependencies["vector_repository"].retrieve_vector.assert_not_awaited()
    mock_dependencies["embedding_service"].embed_resume.assert_called_once_with(
        parsed_resume
    )


@pytest.mark.asyncio
async def test_recommend_jobs_retrieve_payload_skills_build_parsed_resume(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    target_job_id = uuid.uuid4()

    mock_dependencies["vector_repository"].retrieve_vector.return_value = {
        "id": str(cand_id),
        "vector": [0.3] * 384,
        "payload": {"skills": ["Python", "SQL"]},
    }
    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_job_id),
            "score": 0.8,
            "payload": {"skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        MatchResultSchema(
            overall_score=80.0,
            cosine_similarity=0.8,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
        )
    )

    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id, limit=5
    )

    resume_arg = mock_dependencies[
        "matching_engine"
    ].match_resume_to_job.call_args.kwargs["resume"]
    assert resume_arg.skills == ["Python", "SQL"]


@pytest.mark.asyncio
async def test_recommend_jobs_retrieve_payload_preserves_parsed_resume(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    target_job_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(
        full_name="Jane",
        skills=["Python", "SQL"],
        total_years_experience=4.0,
    )

    mock_dependencies["vector_repository"].retrieve_vector.return_value = {
        "id": str(cand_id),
        "vector": [0.3] * 384,
        "payload": {"skills": ["Python", "SQL"]},
    }
    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_job_id),
            "score": 0.8,
            "payload": {"skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        MatchResultSchema(
            overall_score=80.0,
            cosine_similarity=0.8,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
        )
    )

    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        parsed_resume=parsed_resume,
        limit=5,
    )

    assert len(recs) == 1
    resume_arg = mock_dependencies[
        "matching_engine"
    ].match_resume_to_job.call_args.kwargs["resume"]
    assert resume_arg is parsed_resume
    assert resume_arg.total_years_experience == 4.0


@pytest.mark.asyncio
async def test_recommend_candidates_calls_retrieve_vector_when_no_vector(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    target_cand_id = uuid.uuid4()

    mock_dependencies["vector_repository"].retrieve_vector.return_value = {
        "id": str(job_id),
        "vector": [0.2] * 384,
        "payload": {"job_id": str(job_id), "skills": ["Python"]},
    }
    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_cand_id),
            "score": 0.85,
            "payload": {"candidate_id": str(target_cand_id), "skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        MatchResultSchema(
            overall_score=85.0,
            cosine_similarity=0.85,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
        )
    )

    recs = await ai_service.recommend_candidates_for_job(
        job_id=job_id, limit=5
    )

    mock_dependencies[
        "vector_repository"
    ].retrieve_vector.assert_awaited_once_with(
        collection_name="jobs", point_id=job_id
    )
    assert len(recs) == 1
    assert recs[0].candidate_id == target_cand_id


@pytest.mark.asyncio
async def test_recommend_candidates_retrieve_missing_raises_not_found(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    mock_dependencies["vector_repository"].retrieve_vector.return_value = None

    with pytest.raises(EntityNotFoundException):
        await ai_service.recommend_candidates_for_job(
            job_id=job_id, limit=5
        )


@pytest.mark.asyncio
async def test_recommend_candidates_explicit_vector_skips_retrieve(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    target_cand_id = uuid.uuid4()

    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_cand_id),
            "score": 0.8,
            "payload": {"candidate_id": str(target_cand_id), "skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        MatchResultSchema(
            overall_score=80.0,
            cosine_similarity=0.8,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
        )
    )

    await ai_service.recommend_candidates_for_job(
        job_id=job_id,
        job_vector=[0.6] * 384,
        limit=5,
    )

    mock_dependencies["vector_repository"].retrieve_vector.assert_not_awaited()
    mock_dependencies[
        "vector_repository"
    ].search_similar.assert_awaited_once_with(
        collection_name="resumes",
        query_vector=[0.6] * 384,
        limit=5,
    )


@pytest.mark.asyncio
async def test_recommend_candidates_retrieve_payload_skills_build_parsed_job(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    target_cand_id = uuid.uuid4()

    mock_dependencies["vector_repository"].retrieve_vector.return_value = {
        "id": str(job_id),
        "vector": [0.2] * 384,
        "payload": {"job_id": str(job_id), "skills": ["Python"]},
    }
    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(target_cand_id),
            "score": 0.8,
            "payload": {"candidate_id": str(target_cand_id), "skills": ["Python"]},
            "vector": [0.1] * 384,
        }
    ]
    mock_dependencies["matching_engine"].match_resume_to_job.return_value = (
        MatchResultSchema(
            overall_score=80.0,
            cosine_similarity=0.8,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
        )
    )

    recs = await ai_service.recommend_candidates_for_job(
        job_id=job_id, limit=5
    )

    job_arg = mock_dependencies[
        "matching_engine"
    ].match_resume_to_job.call_args.kwargs["job"]
    assert job_arg.required_skills == ["Python"]
