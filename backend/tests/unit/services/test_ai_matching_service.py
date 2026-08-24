from __future__ import annotations

import asyncio
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
from app.models import CandidateProfile, Resume
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
        collection_name="jobs", query_vector=[0.1] * 384, limit=50
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
        limit=50,
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

    recs = await ai_service.recommend_candidates_for_job(
        job_id=job_id, limit=5
    )

    job_arg = mock_dependencies[
        "matching_engine"
    ].match_resume_to_job.call_args.kwargs["job"]
    assert job_arg.required_skills == ["Python"]


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

    assert len(recs) == 1
    assert recs[0].parsed_resume.full_name is None
    assert recs[0].parsed_resume.skills == ["Python"]


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

    recs = asyncio.run(
        ai_service.recommend_candidates_for_job(
            job_id=job_id,
            job_vector=[0.5] * 384,
            limit=5,
        )
    )

    assert len(recs) == 1
    assert recs[0].parsed_resume.full_name is None
    assert recs[0].parsed_resume.skills == ["Python"]


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
