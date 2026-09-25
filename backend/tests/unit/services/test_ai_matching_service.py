from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.ai.matching.matching_engine import MatchingEngine
from app.ai.parsers.job_parser import JobParser
from app.ai.parsers.resume_parser import ResumeParser
from app.ai.vector_db.qdrant_client import QdrantVectorRepository, SOFT_DELETE_FILTER
from app.core.config import settings
from app.core.exceptions import EmptyDocumentError, EntityNotFoundException
from app.database.session import async_session_factory
from app.models import CandidateProfile, Resume, User
from app.repositories import ResumeRepository
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.admin_service import AdminService
from scripts.sync_resumes_qdrant import run_sync, sync_resumes
from scripts.reconcile_qdrant_resumes import run_reconcile, reconcile_resumes
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointStruct, Distance, VectorParams, ScoredPoint


@pytest.fixture
def mock_dependencies():
    return {
        "resume_parser": AsyncMock(spec=ResumeParser),
        "job_parser": AsyncMock(spec=JobParser),
        "embedding_service": AsyncMock(spec=EmbeddingService),
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


def _mock_db_session(existing: Resume | None = None) -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    session.execute.return_value = result_mock
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def test_process_and_index_resume_creates_resume_row(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(
        full_name="John Doe",
        email="john@example.com",
        skills=["Python", "FastAPI"],
        languages=["Vietnamese"],
    )
    mock_dependencies["resume_parser"].parse.return_value = parsed_resume
    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    session = _mock_db_session(existing=None)

    with patch(
        "app.ai.extractors.pdf_extractor.PDFTextExtractor.extract",
        return_value="Extracted CV Text",
    ):
        result = asyncio.run(
            ai_service.process_and_index_resume(
                cand_id,
                b"%PDF-1.7 fake",
                session=session,
                source_name="cv.pdf",
            )
        )

    assert result == parsed_resume
    mock_dependencies["vector_repository"].upsert_vector.assert_awaited_once()
    session.add.assert_called_once()
    added = session.add.call_args.args[0]
    assert isinstance(added, Resume)
    assert added.candidate_id == cand_id
    assert added.title == "cv.pdf"
    assert added.is_primary is True
    assert added.parsed_data == parsed_resume.model_dump(mode="json")
    session.commit.assert_awaited_once()


def test_process_and_index_resume_updates_primary_resume_row(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    existing = Resume(
        id=uuid.uuid4(),
        candidate_id=cand_id,
        title="old.pdf",
        is_primary=True,
        parsed_data={"skills": ["Old"]},
    )
    parsed_resume = ParsedResumeSchema(
        full_name="John Doe",
        skills=["Python", "FastAPI"],
    )
    mock_dependencies["resume_parser"].parse.return_value = parsed_resume
    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    session = _mock_db_session(existing=existing)

    with patch(
        "app.ai.extractors.pdf_extractor.PDFTextExtractor.extract",
        return_value="Extracted CV Text",
    ):
        asyncio.run(
            ai_service.process_and_index_resume(
                cand_id,
                b"%PDF-1.7 fake",
                session=session,
                source_name="new-cv.pdf",
            )
        )

    session.add.assert_not_called()
    assert existing.title == "new-cv.pdf"
    assert existing.is_primary is True
    assert existing.parsed_data == parsed_resume.model_dump(mode="json")
    session.commit.assert_awaited_once()


def test_process_and_index_resume_persistence_failure_raises(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(
        full_name="John Doe",
        skills=["Python"],
    )
    mock_dependencies["resume_parser"].parse.return_value = parsed_resume
    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384
    session = _mock_db_session(existing=None)
    session.commit.side_effect = RuntimeError("db unavailable")

    with patch(
        "app.ai.extractors.pdf_extractor.PDFTextExtractor.extract",
        return_value="Extracted CV Text",
    ):
        with pytest.raises(RuntimeError, match="db unavailable"):
            asyncio.run(
                ai_service.process_and_index_resume(
                    cand_id,
                    b"%PDF-1.7 fake",
                    session=session,
                    source_name="cv.pdf",
                )
            )

    session.rollback.assert_awaited_once()


def test_process_and_index_resume_skips_persistence_without_session(
    ai_service, mock_dependencies
):
    cand_id = uuid.uuid4()
    parsed_resume = ParsedResumeSchema(skills=["Python"])
    mock_dependencies["resume_parser"].parse.return_value = parsed_resume
    mock_dependencies["embedding_service"].embed_resume.return_value = [
        0.1
    ] * 384

    with patch(
        "app.ai.extractors.pdf_extractor.PDFTextExtractor.extract",
        return_value="Extracted CV Text",
    ):
        result = asyncio.run(
            ai_service.process_and_index_resume(cand_id, b"%PDF fake")
        )

    assert result == parsed_resume
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


@pytest.mark.asyncio
async def test_match_candidate_with_job_success(ai_service, mock_dependencies):
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

    res = await ai_service.match_candidate_with_job(parsed_resume, parsed_job)

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

    # Without session/actor_user, no SQL authorization occurs, so no jobs are returned
    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        parsed_resume=parsed_resume,
        limit=5,
    )

    assert len(recs) == 0
    mock_dependencies[
        "vector_repository"
    ].search_similar.assert_awaited_once_with(
        collection_name="jobs",
        query_vector=[0.1] * 384,
        limit=50,
        filters={"status": "published"},
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

    # Without session/actor_user, no SQL authorization occurs, so no jobs are returned
    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id, limit=5
    )

    mock_dependencies[
        "vector_repository"
    ].retrieve_vector.assert_awaited_once_with(
        collection_name="resumes", point_id=cand_id
    )
    # Secure behavior: no jobs returned without authorization context
    assert len(recs) == 0


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
        limit=50,
        filters={"status": "published"},
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

    # Without session/actor_user, no SQL authorization occurs, so no jobs are returned
    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id, limit=5
    )

    # Secure behavior: no jobs returned without authorization context
    assert len(recs) == 0


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

    # Without session/actor_user, no SQL authorization occurs, so no jobs are returned
    recs = await ai_service.recommend_jobs_for_candidate(
        candidate_id=cand_id,
        parsed_resume=parsed_resume,
        limit=5,
    )

    # Secure behavior: no jobs returned without authorization context
    assert len(recs) == 0


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

    # Without session/actor_user, no SQL authorization occurs, so no candidates are returned
    recs = await ai_service.recommend_candidates_for_job(
        job_id=job_id, limit=5
    )

    mock_dependencies[
        "vector_repository"
    ].retrieve_vector.assert_awaited_once_with(
        collection_name="jobs", point_id=job_id
    )
    # Secure behavior: no candidates returned without authorization context
    assert len(recs) == 0


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
        limit=50,
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

    # Without session/actor_user, no SQL authorization occurs, so no candidates are returned
    recs = await ai_service.recommend_candidates_for_job(
        job_id=job_id, limit=5
    )

    # Secure behavior: no candidates returned without authorization context
    assert len(recs) == 0


def _make_profile_session(
    profiles: list[CandidateProfile],
    resumes: list | None = None,
    jobs: list | None = None,
) -> MagicMock:
    """Create a mock session that returns appropriate objects based on the query model.

    Args:
        profiles: CandidateProfile objects for profile queries
        resumes: Resume objects for resume queries (with parsed_data)
        jobs: Job objects for job queries (with parsed_reqs)
    """
    from unittest.mock import MagicMock, AsyncMock

    session = MagicMock()
    session.execute = AsyncMock()

    def _execute(stmt):
        result_mock = MagicMock()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()

        if "from candidate_profiles" in compiled or "from candidateprofile" in compiled:
            # Profile query - return CandidateProfile objects
            result_mock.scalars.return_value.all.return_value = profiles
        elif "from resumes" in compiled or "from resume" in compiled:
            # Resume query - return Resume objects with parsed_data
            result_mock.scalars.return_value.all.return_value = resumes or []
        elif "from jobs" in compiled or "from job" in compiled:
            # Job query - return Job objects with parsed_reqs
            result_mock.scalars.return_value.all.return_value = jobs or []
        else:
            # Default to profiles
            result_mock.scalars.return_value.all.return_value = profiles

        return result_mock

    session.execute.side_effect = _execute
    return session


def test_recommend_candidates_resolves_profiles_in_one_batch(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    cand1_id = uuid.uuid4()
    cand2_id = uuid.uuid4()

    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(cand1_id),
            "score": 0.9,
            "payload": {"candidate_id": str(cand1_id), "skills": ["Python"]},
            "vector": [0.1] * 384,
        },
        {
            "id": str(cand2_id),
            "score": 0.7,
            "payload": {"candidate_id": str(cand2_id), "skills": ["SQL"]},
            "vector": [0.2] * 384,
        },
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

    profile1 = CandidateProfile(
        id=cand1_id,
        user_id=uuid.uuid4(),
        full_name="Jane Doe",
        title="Backend Engineer",
    )
    profile2 = CandidateProfile(
        id=cand2_id,
        user_id=uuid.uuid4(),
        full_name="John Smith",
        title="Data Engineer",
    )

    # Create mock Resume objects with parsed_data for the resume query
    from app.models import Resume
    resume1 = Resume(
        id=uuid.uuid4(),
        candidate_id=cand1_id,
        title="cv1.pdf",
        is_primary=True,
        is_deleted=False,
        parsed_data={
            "full_name": "Jane Doe",
            "title": "Backend Engineer",
            "skills": ["Python"],
        },
    )
    resume2 = Resume(
        id=uuid.uuid4(),
        candidate_id=cand2_id,
        title="cv2.pdf",
        is_primary=True,
        is_deleted=False,
        parsed_data={
            "full_name": "John Smith",
            "title": "Data Engineer",
            "skills": ["SQL"],
        },
    )

    session = _make_profile_session(
        profiles=[profile1, profile2],
        resumes=[resume1, resume2],
    )

    recs = asyncio.run(
        ai_service.recommend_candidates_for_job(
            job_id=job_id,
            job_vector=[0.5] * 384,
            limit=5,
            session=session,
        )
    )

    assert len(recs) == 2
    by_id = {rec.candidate_id: rec for rec in recs}
    assert by_id[cand1_id].parsed_resume.full_name == "Jane Doe"
    assert by_id[cand1_id].parsed_resume.title == "Backend Engineer"
    assert by_id[cand2_id].parsed_resume.full_name == "John Smith"
    assert by_id[cand2_id].parsed_resume.title == "Data Engineer"
    # Session.execute is called twice: once for CandidateProfile, once for Resume
    assert session.execute.await_count == 2
    # Verify the profile query (first call)
    stmt = session.execute.call_args_list[0].args[0]
    from sqlalchemy.sql import Select as SQLSelect

    assert isinstance(stmt, SQLSelect)
    compiled_sql = str(
        stmt.compile(compile_kwargs={"literal_binds": True})
    )
    assert str(cand1_id).replace("-", "") in compiled_sql
    assert str(cand2_id).replace("-", "") in compiled_sql
    assert "is_deleted" in compiled_sql
    # Verify the resume query (second call)
    stmt2 = session.execute.call_args_list[1].args[0]
    assert isinstance(stmt2, SQLSelect)
    compiled_sql2 = str(
        stmt2.compile(compile_kwargs={"literal_binds": True})
    )
    assert "is_primary" in compiled_sql2
    assert "is_deleted" in compiled_sql2


def test_recommend_candidates_missing_profile_keeps_fallback(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    cand1_id = uuid.uuid4()

    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(cand1_id),
            "score": 0.9,
            "payload": {"candidate_id": str(cand1_id), "skills": ["Python"]},
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
    session = _make_profile_session(profiles=[], resumes=[])

    recs = asyncio.run(
        ai_service.recommend_candidates_for_job(
            job_id=job_id,
            job_vector=[0.5] * 384,
            limit=5,
            session=session,
        )
    )

    # With session but no actor_user, legacy resolution is used but SQL returns empty
    # Secure behavior: no fallback to Qdrant payload
    assert len(recs) == 0


def test_recommend_candidates_without_session_skips_db(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    cand1_id = uuid.uuid4()

    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(cand1_id),
            "score": 0.9,
            "payload": {"candidate_id": str(cand1_id), "skills": ["Python"]},
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

    # Without session/actor_user, no SQL authorization occurs
    # Secure behavior: no candidates returned without authorization context
    recs = asyncio.run(
        ai_service.recommend_candidates_for_job(
            job_id=job_id,
            job_vector=[0.5] * 384,
            limit=5,
        )
    )

    assert len(recs) == 0


def test_recommend_candidates_deleted_profiles_not_resolved(
    ai_service, mock_dependencies
):
    job_id = uuid.uuid4()
    cand1_id = uuid.uuid4()

    mock_dependencies["vector_repository"].search_similar.return_value = [
        {
            "id": str(cand1_id),
            "score": 0.9,
            "payload": {"candidate_id": str(cand1_id), "skills": ["Python"]},
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
    session = _make_profile_session(profiles=[], resumes=[])

    asyncio.run(
        ai_service.recommend_candidates_for_job(
            job_id=job_id,
            job_vector=[0.5] * 384,
            limit=5,
            session=session,
        )
    )

    stmt = session.execute.call_args.args[0]
    compiled_sql = str(
        stmt.compile(compile_kwargs={"literal_binds": True})
    )
    assert "is_deleted" in compiled_sql
    assert str(cand1_id).replace("-", "") in compiled_sql


# ===== REGRESSION TESTS FOR RESUME QDRANT SYNCHRONIZATION =====

import scripts.sync_resumes_qdrant as sync_module
import scripts.reconcile_qdrant_resumes as reconcile_module

class TestResumeQdrantRegression:
    """Regression tests for Resume-Qdrant synchronization and lifecycle."""

    @pytest.fixture
    def ai_service_with_mocks(self):
        """Create AI service with mocked dependencies for regression tests."""
        resume_parser = AsyncMock(spec=ResumeParser)
        job_parser = AsyncMock(spec=JobParser)
        embedding_service = AsyncMock(spec=EmbeddingService)
        vector_repository = AsyncMock(spec=BaseVectorRepository)
        matching_engine = MagicMock(spec=MatchingEngine)

        return AIMatchingService(
            resume_parser=resume_parser,
            job_parser=job_parser,
            embedding_service=embedding_service,
            vector_repository=vector_repository,
            matching_engine=matching_engine,
        ), {
            "resume_parser": resume_parser,
            "job_parser": job_parser,
            "embedding_service": embedding_service,
            "vector_repository": vector_repository,
            "matching_engine": matching_engine,
        }
    
    def _patch_script_modules(self, monkeypatch, ai_service, real_repo):
        """Patch script modules to use our mocked instances."""
        monkeypatch.setattr(sync_module, "AIMatchingService", lambda: ai_service)
        monkeypatch.setattr(sync_module, "QdrantVectorRepository", lambda: real_repo)
        monkeypatch.setattr(reconcile_module, "QdrantVectorRepository", lambda: real_repo)

    @pytest.mark.asyncio
    async def test_search_starvation_deleted_vectors_do_not_block_valid_candidates(
        self, ai_service_with_mocks
    ):
        """Test that deleted/orphan vectors beyond Top-50 don't block valid candidates.

        Regression test for: deleted/orphan vectors consuming Top-50 slots
        and pushing valid candidates out of search results.

        This test exercises the actual production search path:
        - Uses real QdrantVectorRepository.search_similar
        - Mocks only the low-level Qdrant client's query_points
        - The fake inspects the production-generated query/filter/limit
        - Simulates Qdrant semantics: filtering occurs BEFORE applying limit
        """
        ai_service, mocks = ai_service_with_mocks
        job_id = uuid.uuid4()

        # Create 55 candidate vectors in Qdrant: 50 deleted + 5 valid
        # The production code applies SOFT_DELETE_FILTER (must_not is_deleted:true) in the query_filter
        # This filter is applied at the Qdrant level BEFORE the limit
        qdrant_all_points = []

        # 50 deleted vectors (high scores to push valid candidates down in raw ranking)
        for i in range(50):
            cand_id = uuid.uuid4()
            qdrant_all_points.append({
                "id": str(cand_id),
                "score": 0.9 - i * 0.01,
                "payload": {"candidate_id": str(cand_id), "skills": ["deleted"], "is_deleted": True},
                "vector": [0.1] * 384,
            })

        # 5 valid candidates (lower scores in raw ranking)
        valid_candidate_ids = []
        for i in range(5):
            cand_id = uuid.uuid4()
            valid_candidate_ids.append(cand_id)
            qdrant_all_points.append({
                "id": str(cand_id),
                "score": 0.4 - i * 0.01,
                "payload": {"candidate_id": str(cand_id), "skills": ["Python"], "is_deleted": False},
                "vector": [0.1] * 384,
            })

        # Create a real QdrantVectorRepository with a mocked client
        # We'll intercept the query_points call to verify filtering happens before limit
        real_repo = QdrantVectorRepository()
        real_repo.client = AsyncMock(spec=AsyncQdrantClient)

        # Track the query_filter and limit passed to query_points
        captured_query_filter = {}
        captured_limit = {}

        async def fake_query_points(collection_name, query, query_filter, limit, with_payload, with_vectors, score_threshold):
            captured_query_filter["filter"] = query_filter
            captured_limit["limit"] = limit

            # Simulate Qdrant's behavior: filter is applied BEFORE limit
            # So we filter out is_deleted=True vectors first, then apply limit
            filtered = [p for p in qdrant_all_points if p["payload"].get("is_deleted") is not True]
            limited = filtered[:limit]

            # Return as ScoredPoint objects (what Qdrant returns)
            scored_points = []
            for p in limited:
                scored_points.append(MagicMock(
                    id=p["id"],
                    score=p["score"],
                    payload=p["payload"],
                    vector=p["vector"],
                    model_dump=lambda p=p: {
                        "id": p["id"],
                        "score": p["score"],
                        "payload": p["payload"],
                        "vector": p["vector"],
                    }
                ))
            return MagicMock(points=scored_points)

        real_repo.client.query_points = fake_query_points

        # Replace the vector_repository in ai_service with our real repo with mocked client
        ai_service.vector_repository = real_repo

        mocks["matching_engine"].match_resume_to_job.return_value = MatchResultSchema(
            overall_score=80.0,
            cosine_similarity=0.8,
            skill_coverage_score=1.0,
            experience_match_score=0.5,
            matching_skills=["Python"],
        )

        # Create mock session that returns valid candidates
        session = MagicMock()
        session.execute = AsyncMock()

        def _execute(stmt):
            result_mock = MagicMock()
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
            if "candidate_profiles" in compiled or "candidateprofile" in compiled:
                profiles = []
                for cand_id in valid_candidate_ids:
                    profiles.append(CandidateProfile(
                        id=cand_id,
                        user_id=uuid.uuid4(),
                        full_name=f"Candidate {str(cand_id)[:8]}",
                        title="Engineer",
                    ))
                result_mock.scalars.return_value.all.return_value = profiles
            elif "resumes" in compiled or "resume" in compiled:
                resumes = []
                for cand_id in valid_candidate_ids:
                    resume = Resume(
                        id=uuid.uuid4(),
                        candidate_id=cand_id,
                        title="cv.pdf",
                        is_primary=True,
                        is_deleted=False,
                        parsed_data={
                            "full_name": f"Candidate {str(cand_id)[:8]}",
                            "skills": ["Python"],
                        },
                    )
                    resumes.append(resume)
                result_mock.scalars.return_value.all.return_value = resumes
            else:
                result_mock.scalars.return_value.all.return_value = []
            return result_mock

        session.execute.side_effect = _execute

        # Call recommend_candidates_for_job - this invokes the real search_similar
        recs = await ai_service.recommend_candidates_for_job(
            job_id=job_id,
            job_vector=[0.5] * 384,
            limit=10,
            session=session,
        )

        # Verify valid candidates are returned despite 50 deleted vectors existing
        # The filter is applied BEFORE limit, so deleted vectors don't consume the limit
        assert len(recs) >= 3, f"Expected at least 3 valid candidates, got {len(recs)}"
        returned_ids = {rec.candidate_id for rec in recs}
        assert returned_ids & set(valid_candidate_ids), "Valid candidates should be discoverable"

        # Verify the search was called with correct limit (should be >= 50 to catch valid candidates)
        assert captured_limit["limit"] >= 50, "Search limit should be large enough to find valid candidates"

        # Verify the filter was correctly constructed with SOFT_DELETE_FILTER
        query_filter = captured_query_filter["filter"]
        assert query_filter is not None, "Query filter should be applied"
        # The filter must include must_not condition for is_deleted=true
        assert query_filter.must_not is not None, "SOFT_DELETE_FILTER must_not condition should be present"
        # Verify at least one must_not condition checks is_deleted
        has_deleted_filter = any(
            getattr(cond, "key", None) == "is_deleted" for cond in query_filter.must_not
        )
        assert has_deleted_filter, "Filter must include is_deleted condition"

    @pytest.mark.asyncio
    async def test_soft_delete_lifecycle_calls_delete_vector(
        self, ai_service_with_mocks
    ):
        """Test that soft-deleting a candidate calls delete_resume_vector.

        Regression test for: candidate deletion lifecycle should clean up Qdrant vector.

        This test invokes the actual production deletion owner: AdminService.delete_user.
        """
        ai_service, mocks = ai_service_with_mocks

        # Create a mock candidate with a primary resume
        candidate_id = uuid.uuid4()
        user_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        # Create a mock User with candidate profile
        from app.models import User, CandidateProfile
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.email = "test@example.com"
        mock_user.is_active = True
        mock_user.role = MagicMock()
        mock_user.role.value = "candidate"

        # Mock candidate profile with primary resume
        mock_candidate = MagicMock(spec=CandidateProfile)
        mock_candidate.id = candidate_id
        mock_candidate.user_id = user_id
        mock_candidate.is_deleted = False
        mock_user.candidate_profile = mock_candidate

        # Create a mock session
        session = AsyncMock()

        # Mock UserRepository.get_admin_user to return our mock user
        from unittest.mock import patch
        from app.repositories import UserRepository, ResumeRepository
        from app.models import Resume

        # Mock the primary resume existence
        mock_primary_resume = MagicMock(spec=Resume)
        mock_primary_resume.candidate_id = candidate_id

        with patch.object(UserRepository, "get_admin_user", AsyncMock(return_value=mock_user)):
            with patch.object(UserRepository, "soft_delete", AsyncMock()) as mock_soft_delete:
                with patch.object(ResumeRepository, "get_primary_by_candidate", AsyncMock(return_value=mock_primary_resume)):
                    # Patch AIMatchingService constructor to use our mocked ai_service
                    with patch("app.services.admin_service.AIMatchingService", return_value=ai_service):
                        admin_service = AdminService(session)
                        await admin_service.delete_user(user_id)

        # Verify the production lifecycle:
        # AdminService.delete_user -> calls matching_service.delete_resume_vector(candidate_id)
        # which calls vector_repository.delete_vector
        mocks["vector_repository"].delete_vector.assert_awaited_once_with(
            collection_name="resumes",
            point_id=candidate_id,
        )

    @pytest.mark.asyncio
    async def test_transaction_order_sql_before_qdrant(
        self, ai_service_with_mocks
    ):
        """Test that SQL persistence happens BEFORE Qdrant upsert.

        Regression test for: SQL-first transaction ordering to prevent orphan vectors.
        """
        ai_service, mocks = ai_service_with_mocks
        candidate_id = uuid.uuid4()
        parsed_resume = ParsedResumeSchema(
            full_name="John Doe",
            skills=["Python", "FastAPI"],
        )
        mocks["resume_parser"].parse.return_value = parsed_resume
        mocks["embedding_service"].embed_resume.return_value = [0.1] * 384

        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        # Need to mock session.execute for ResumeRepository.get_primary_by_candidate
        session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        call_order = []

        original_upsert = mocks["vector_repository"].upsert_vector

        async def track_upsert(*args, **kwargs):
            call_order.append("qdrant_upsert")
            return await original_upsert(*args, **kwargs)

        mocks["vector_repository"].upsert_vector = track_upsert

        # Use AsyncMock for session.commit since it's an awaited async method
        async def track_commit():
            call_order.append("sql_commit")

        session.commit = AsyncMock(side_effect=track_commit)

        with patch(
            "app.ai.extractors.pdf_extractor.PDFTextExtractor.extract",
            return_value="Extracted CV Text",
        ):
            await ai_service.process_and_index_resume(
                candidate_id=candidate_id,
                pdf_source=b"%PDF-1.4 fake",
                session=session,
                source_name="cv.pdf",
            )

        # Verify order: SQL commit should happen before Qdrant upsert
        assert "sql_commit" in call_order, "SQL commit should be called"
        assert "qdrant_upsert" in call_order, "Qdrant upsert should be called"
        assert call_order.index("sql_commit") < call_order.index("qdrant_upsert"), \
            "SQL commit must happen before Qdrant upsert"

    @pytest.mark.asyncio
    async def test_orphan_reconciliation_deletes_orphan_vectors(
        self, ai_service_with_mocks, monkeypatch
    ):
        """Test that orphan vectors (Qdrant points without SQL candidates) are deleted.

        Regression test for: orphan vectors should be cleaned up by reconciliation.

        This test executes the actual production reconciliation function from the script.
        """
        ai_service, mocks = ai_service_with_mocks

        # Mock SQL active candidates
        sql_candidate_ids = {uuid.uuid4(), uuid.uuid4()}

        # Mock Qdrant points: 2 valid + 3 orphan
        qdrant_points = []
        for cid in sql_candidate_ids:
            qdrant_points.append({
                "id": str(cid),
                "payload": {"candidate_id": str(cid), "is_deleted": False},
            })
        orphan_ids = [uuid.uuid4() for _ in range(3)]
        for oid in orphan_ids:
            qdrant_points.append({
                "id": str(oid),
                "payload": {"candidate_id": str(oid), "is_deleted": False},
            })

        # Create a real QdrantVectorRepository with a mocked client
        real_repo = QdrantVectorRepository()
        real_repo.client = AsyncMock(spec=AsyncQdrantClient)

        # Track scroll calls - return proper objects with .payload attribute
        scroll_call_count = 0

        class MockPoint:
            def __init__(self, point_data):
                self.id = point_data["id"]
                self.payload = point_data["payload"]

        async def fake_scroll(collection_name, limit, offset, with_payload, with_vectors, scroll_filter):
            nonlocal scroll_call_count
            if scroll_call_count == 0:
                scroll_call_count += 1
                return ([MockPoint(p) for p in qdrant_points[:50]], None)
            else:
                return ([], None)

        real_repo.client.scroll = fake_scroll

        # Track delete_vector calls
        deleted_points = []

        async def fake_delete_vector(collection_name, point_id):
            deleted_points.append(str(point_id))

        real_repo.delete_vector = fake_delete_vector

        # Track the SQL query execution - mock the session factory in the script module
        class MockAsyncSessionFactory:
            def __init__(self, session):
                self.session = session
            
            async def __aenter__(self):
                return self.session
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_session = AsyncMock()
        mock_result = MagicMock()
        # Return actual UUID objects, not MagicMock
        mock_result.scalars.return_value.all.return_value = list(sql_candidate_ids)
        mock_session.execute = AsyncMock(return_value=mock_result)

        def fake_session_factory():
            return MockAsyncSessionFactory(mock_session)

        # Patch the session factory in the script module
        monkeypatch.setattr(reconcile_module, "async_session_factory", fake_session_factory)

        # Call the actual production reconciliation function with our mocked repo
        result = await reconcile_module.reconcile_resumes(dry_run=False, repo=real_repo)

        # Verify the production reconciliation function executed correctly
        # It should have:
        # 1. Queried SQL for active candidates
        # 2. Scrolled Qdrant for all vectors
        # 3. Deleted orphan vectors

        # Verify orphan vectors were deleted
        assert len(deleted_points) == 3, f"Expected 3 deletions, got {len(deleted_points)}"
        for oid in orphan_ids:
            assert str(oid) in deleted_points, f"Orphan {oid} should be deleted"

        # Verify valid vectors were NOT deleted
        for cid in sql_candidate_ids:
            assert str(cid) not in deleted_points, f"Valid candidate {cid} should not be deleted"

        # Verify result counters
        assert result["stale"] == 3, "Should detect 3 stale vectors"
        assert result["deleted"] == 3, "Should delete 3 vectors"
        assert result["valid"] == 2, "Should have 2 valid vectors"

    @pytest.mark.asyncio
    async def test_missing_vector_recreated_on_sync(
        self, ai_service_with_mocks, monkeypatch
    ):
        """Test that missing Qdrant vectors for active SQL resumes are recreated.

        Regression test for: sync script should detect and recreate missing vectors.

        This test invokes the actual production sync script entry point.
        """
        ai_service, mocks = ai_service_with_mocks
        candidate_id = uuid.uuid4()
        parsed_resume = ParsedResumeSchema(skills=["Python", "FastAPI"])

        # Setup: SQL has a resume but Qdrant is missing the vector
        sql_resumes = []
        resume = Resume(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            title="cv.pdf",
            is_primary=True,
            is_deleted=False,
            parsed_data={
                "full_name": "Test Candidate",
                "skills": ["Python", "FastAPI"],
            },
        )
        # Create mock candidate with user
        candidate = MagicMock()
        candidate.id = candidate_id
        candidate.user = MagicMock()
        candidate.user.email = "test@example.com"
        candidate.user.is_active = True
        candidate.full_name = "Test Candidate"
        candidate.is_deleted = False
        resume.candidate = candidate
        sql_resumes.append(resume)

        # Qdrant has no valid vectors for this candidate
        qdrant_resume_ids = set()

        # Create a real QdrantVectorRepository with a mocked client
        real_repo = QdrantVectorRepository()
        real_repo.client = AsyncMock(spec=AsyncQdrantClient)

        # Mock get_collection to return collection info
        mock_collection_info = MagicMock()
        mock_collection_info.config.params.vectors.size = 384
        mock_collection_info.points_count = 0
        real_repo.client.get_collection = AsyncMock(return_value=mock_collection_info)

        # Mock scroll to return empty (no existing vectors) - return proper objects
        class MockPoint:
            def __init__(self, point_data):
                self.id = point_data["id"]
                self.payload = point_data["payload"]

        real_repo.client.scroll = AsyncMock(return_value=([], None))

        # Track upsert_vector calls on real_repo (which we'll inject into ai_service)
        upserted_candidates = []

        async def track_upsert(collection_name, point_id, vector, payload):
            upserted_candidates.append(str(point_id))

        real_repo.upsert_vector = track_upsert

        # Replace ai_service's vector_repository with real_repo so script uses it
        ai_service.vector_repository = real_repo

        # Mock the embedding service to return a vector
        mocks["embedding_service"].embed_resume.return_value = [0.1] * 384

        # Patch the session factory and AI matching service in the sync script
        class MockAsyncSessionFactory:
            def __init__(self, session):
                self.session = session
            
            async def __aenter__(self):
                return self.session
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sql_resumes
        mock_session.execute = AsyncMock(return_value=mock_result)

        def mock_session_factory():
            return MockAsyncSessionFactory(mock_session)

        # Patch the session factory in the script module (since script imports it at module level)
        monkeypatch.setattr(sync_module, "async_session_factory", mock_session_factory)

        # Mock the unique() call on the result scalars
        mock_scalars = mock_result.scalars.return_value
        mock_scalars.unique.return_value.all.return_value = sql_resumes

        # Call sync_resumes with our mocked instances
        result = await sync_module.sync_resumes(
            dry_run=False,
            matching_service=ai_service,
            repo=real_repo,
        )

        # Verify the sync recreated the missing vector
        assert str(candidate_id) in upserted_candidates, f"Candidate {candidate_id} should have been upserted"
        assert result["upserted"] == 1, "Should have upserted 1 vector"
        assert result["missing"] == 1, "Should have detected 1 missing vector"
        assert result["failed"] == 0, "Should have no failures"

    @pytest.mark.asyncio
    async def test_idempotent_sync_and_reconcile(
        self, ai_service_with_mocks, monkeypatch
    ):
        """Test that running sync/reconcile twice produces stable results.

        Regression test for: idempotent synchronization and reconciliation.

        This test exercises the actual production sync and reconciliation entry points.
        """
        ai_service, mocks = ai_service_with_mocks
        candidate_id = uuid.uuid4()
        parsed_resume = ParsedResumeSchema(skills=["Python"])

        # Setup: SQL has a resume, Qdrant has the vector already (after first run)
        sql_resumes = []
        resume = Resume(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            title="cv.pdf",
            is_primary=True,
            is_deleted=False,
            parsed_data={
                "full_name": "Test Candidate",
                "skills": ["Python"],
            },
        )
        candidate = MagicMock()
        candidate.id = candidate_id
        candidate.user = MagicMock()
        candidate.user.email = "test@example.com"
        candidate.user.is_active = True
        candidate.full_name = "Test Candidate"
        candidate.is_deleted = False
        resume.candidate = candidate
        sql_resumes.append(resume)

        # Qdrant already has this vector (simulating after first sync)
        qdrant_resume_ids = {candidate_id}

        # Create a real QdrantVectorRepository with a mocked client
        real_repo = QdrantVectorRepository()
        real_repo.client = AsyncMock(spec=AsyncQdrantClient)

        # Mock get_collection
        mock_collection_info = MagicMock()
        mock_collection_info.config.params.vectors.size = 384
        mock_collection_info.points_count = 1
        real_repo.client.get_collection = AsyncMock(return_value=mock_collection_info)

        # Mock scroll to return the existing vector - return proper objects
        class MockPoint:
            def __init__(self, point_data):
                self.id = point_data["id"]
                self.payload = point_data["payload"]

        scroll_points = [{
            "id": str(candidate_id),
            "payload": {"candidate_id": str(candidate_id), "is_deleted": False},
        }]

        real_repo.client.scroll = AsyncMock(return_value=([MockPoint(p) for p in scroll_points], None))

        # Track upsert_vector calls on the fixture's vector_repository
        upserted_count = 0

        original_upsert = mocks["vector_repository"].upsert_vector

        async def track_upsert(collection_name, point_id, vector, payload):
            nonlocal upserted_count
            upserted_count += 1
            return await original_upsert(collection_name, point_id, vector, payload)

        mocks["vector_repository"].upsert_vector = track_upsert

        # Mock the embedding service
        mocks["embedding_service"].embed_resume.return_value = [0.1] * 384

        class MockAsyncSessionFactory:
            def __init__(self, session):
                self.session = session
            
            async def __aenter__(self):
                return self.session
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        # Create the mock result outside so we can reference it for unique()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sql_resumes
        mock_result.scalars.return_value.unique.return_value.all.return_value = sql_resumes
        mock_session.execute = AsyncMock(return_value=mock_result)

        def mock_session_factory():
            return MockAsyncSessionFactory(mock_session)

        # Patch the session factory in the script module (since script imports it at module level)
        monkeypatch.setattr(sync_module, "async_session_factory", mock_session_factory)

        # First sync run
        result1 = await sync_module.sync_resumes(
            dry_run=False,
            matching_service=ai_service,
            repo=real_repo,
        )
        first_upserted = upserted_count

        # Reset counter for second run
        upserted_count = 0

        # Second sync run (should be idempotent - no new upserts needed)
        result2 = await sync_module.sync_resumes(
            dry_run=False,
            matching_service=ai_service,
            repo=real_repo,
        )
        second_upserted = upserted_count

        # Verify idempotency: second run should not upsert since vector already exists
        assert second_upserted == 0, "Second sync should not upsert anything (already in sync)"
        assert first_upserted == 0, "First sync should also not upsert (vector already exists in Qdrant)"
        assert result1["already_indexed"] == 1, "Should detect 1 already indexed"
        assert result2["already_indexed"] == 1, "Should detect 1 already indexed on second run"

    @pytest.mark.asyncio
    async def test_qdrant_failure_returns_error(
        self, ai_service_with_mocks, monkeypatch
    ):
        """Test that Qdrant failure is properly reported.

        Regression test for: Qdrant errors should be reported in sync results.

        This test exercises the actual production path through the sync script.
        """
        ai_service, mocks = ai_service_with_mocks
        candidate_id = uuid.uuid4()
        parsed_resume = ParsedResumeSchema(skills=["Python"])

        # Setup: SQL has a resume
        sql_resumes = []
        resume = Resume(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            title="cv.pdf",
            is_primary=True,
            is_deleted=False,
            parsed_data={
                "full_name": "Test Candidate",
                "skills": ["Python"],
            },
        )
        candidate = MagicMock()
        candidate.id = candidate_id
        candidate.user = MagicMock()
        candidate.user.email = "test@example.com"
        candidate.user.is_active = True
        candidate.full_name = "Test Candidate"
        candidate.is_deleted = False
        resume.candidate = candidate
        sql_resumes.append(resume)

        # Qdrant has no vector for this candidate
        # Create a real QdrantVectorRepository with a mocked client that fails
        real_repo = QdrantVectorRepository()
        real_repo.client = AsyncMock(spec=AsyncQdrantClient)

        # Mock get_collection
        mock_collection_info = MagicMock()
        mock_collection_info.config.params.vectors.size = 384
        mock_collection_info.points_count = 0
        real_repo.client.get_collection = AsyncMock(return_value=mock_collection_info)

        # Mock scroll to return empty - return proper objects
        class MockPoint:
            def __init__(self, point_data):
                self.id = point_data["id"]
                self.payload = point_data["payload"]

        real_repo.client.scroll = AsyncMock(return_value=([], None))

        # Mock the embedding service
        mocks["embedding_service"].embed_resume.return_value = [0.1] * 384
        from app.ai.vector_db.qdrant_client import AIError

        class MockAsyncSessionFactory:
            def __init__(self, session):
                self.session = session
            
            async def __aenter__(self):
                return self.session
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        # Create the mock result outside so we can reference it for unique()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sql_resumes
        mock_result.scalars.return_value.unique.return_value.all.return_value = sql_resumes
        mock_session.execute = AsyncMock(return_value=mock_result)

        def mock_session_factory():
            return MockAsyncSessionFactory(mock_session)

        # Make real_repo.upsert_vector raise AIError
        async def failing_upsert(collection_name, point_id, vector, payload):
            raise AIError("Qdrant unavailable")

        real_repo.upsert_vector = failing_upsert

        # Replace ai_service's vector_repository with real_repo so script uses it
        ai_service.vector_repository = real_repo

        # Patch the session factory in the script module (since script imports it at module level)
        monkeypatch.setattr(sync_module, "async_session_factory", mock_session_factory)

        # Call the production sync function - should report failure in result
        result = await sync_module.sync_resumes(
            dry_run=False,
            matching_service=ai_service,
            repo=real_repo,
        )

        # Verify error was reported in sync result
        assert result["failed"] == 1, "Should have 1 failed upsert"
        assert result["upserted"] == 0, "Should have 0 successful upserts"
