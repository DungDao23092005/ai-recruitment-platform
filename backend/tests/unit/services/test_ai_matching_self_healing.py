"""Regression tests for lazy self-healing in AIMatchingService.

These tests verify the self-healing behavior when Qdrant vectors are missing
but primary resumes exist in SQL, ensuring exactly one embedding is computed.
"""
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
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.core.exceptions import EntityNotFoundException
from app.domain.enums import JobStatus
from app.models import Resume
from app.repositories import ResumeRepository
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.ai_matching_service import AIMatchingService
from app.services.context_resolver import ContextResolver


@pytest.fixture
def mock_dependencies():
    return {
        "resume_parser": AsyncMock(spec=ResumeParser),
        "job_parser": AsyncMock(spec=JobParser),
        "embedding_service": AsyncMock(spec=EmbeddingService),
        "vector_repository": AsyncMock(spec=BaseVectorRepository),
        "matching_engine": MagicMock(spec=MatchingEngine),
    }


def make_mock_context_resolver(jobs_dict=None, resumes_dict=None):
    """Create a mock ContextResolver that returns predefined data filtered by IDs."""
    resolver = MagicMock(spec=ContextResolver)

    async def mock_resolve_jobs(job_ids, actor_user):
        if not job_ids:
            return {}
        return {jid: jobs_dict[jid] for jid in job_ids if jid in (jobs_dict or {})}

    async def mock_resolve_resumes(candidate_ids, actor_user):
        if not candidate_ids:
            return {}
        return {cid: resumes_dict[cid] for cid in candidate_ids if cid in (resumes_dict or {})}

    resolver.resolve_jobs = AsyncMock(side_effect=mock_resolve_jobs)
    resolver.resolve_resumes = AsyncMock(side_effect=mock_resolve_resumes)
    return resolver


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def sample_parsed_resume():
    """Create a sample parsed resume for testing."""
    return ParsedResumeSchema(
        skills=["Python", "FastAPI", "PostgreSQL"],
        experiences=[
            {
                "title": "Backend Engineer",
                "company": "Tech Corp",
                "duration_months": 24,
            }
        ],
        educations=[
            {
                "degree": "Bachelor",
                "field": "Computer Science",
            }
        ],
    )


@pytest.fixture
def sample_job_data():
    """Create sample job data for recommendations."""
    return [
        (
            uuid.uuid4(),
            ParsedJobSchema(
                title="Senior Backend Engineer",
                required_skills=["Python", "FastAPI"],
                preferred_skills=["PostgreSQL", "Docker"],
            ),
            None,
        )
    ]


@pytest.fixture
def ai_service_with_context_resolver(mock_dependencies, sample_job_data, sample_parsed_resume):
    """Create AIMatchingService with mocked ContextResolver."""
    job_dict = {job_data[0]: job_data[1] for job_data in sample_job_data}
    resume_dict = {uuid.uuid4(): sample_parsed_resume}  # Will be overridden in tests
    context_resolver = make_mock_context_resolver(jobs_dict=job_dict, resumes_dict=resume_dict)

    service = AIMatchingService(
        resume_parser=mock_dependencies["resume_parser"],
        job_parser=mock_dependencies["job_parser"],
        embedding_service=mock_dependencies["embedding_service"],
        vector_repository=mock_dependencies["vector_repository"],
        matching_engine=mock_dependencies["matching_engine"],
        context_resolver=context_resolver,
    )

    return service, context_resolver


class TestLazySelfHealing:
    """Test lazy self-healing when Qdrant vectors are missing."""

    @pytest.mark.asyncio
    async def test_recommend_jobs_missing_vector_self_heals_single_embedding(
        self, ai_service_with_context_resolver, mock_dependencies, mock_session, sample_parsed_resume, sample_job_data
    ):
        """Test self-healing when Qdrant vector is missing but primary resume exists.

        Verifies:
        1. embed_resume() is called EXACTLY ONCE during self-healing
        2. The generated vector is passed to _reindex_resume (avoiding double embedding)
        3. Recommendation succeeds after self-healing
        """
        service, context_resolver = ai_service_with_context_resolver
        candidate_id = uuid.uuid4()
        mock_vector = [0.1] * 384
        job_id_1 = sample_job_data[0][0]

        # Mock search_similar to return job results
        mock_dependencies["vector_repository"].search_similar.return_value = [
            {
                "id": str(job_id_1),
                "vector": [0.2] * 384,
                "payload": {"job_id": str(job_id_1)},
                "score": 0.85,
            }
        ]

        # Setup: Qdrant returns None (missing vector)
        mock_dependencies["vector_repository"].retrieve_vector.return_value = None

        # Update context resolver with this candidate's resume
        context_resolver.resolve_resumes = AsyncMock(
            return_value={candidate_id: sample_parsed_resume}
        )
        context_resolver.resolve_jobs = AsyncMock(
            return_value={job_id_1: sample_job_data[0][1]}
        )

        # Setup: Matching engine returns valid result
        match_result = MatchResultSchema(
            entity_id=sample_job_data[0][0],
            overall_score=85.0,
            cosine_similarity=0.85,
            skill_coverage_score=0.8,
            experience_match_score=0.8,
            matching_skills=["Python", "FastAPI"],
            skill_gap=[],
        )
        mock_dependencies["matching_engine"].match_resume_to_job.return_value = match_result

        # Track embed_resume calls
        embed_call_count = 0

        async def tracking_embed(*args, **kwargs):
            nonlocal embed_call_count
            embed_call_count += 1
            return mock_vector

        mock_dependencies["embedding_service"].embed_resume = tracking_embed

        # Track _reindex_resume calls and verify vector is passed
        reindex_called_with_vector = False

        async def tracking_reindex(candidate_id, parsed_resume, is_deleted=False, vector=None):
            nonlocal reindex_called_with_vector
            if vector is not None:
                reindex_called_with_vector = True
            return None

        service._reindex_resume = tracking_reindex

        # Mock ResumeRepository to return primary resume
        with patch("app.services.ai_matching_service.ResumeRepository") as mock_repo_class:
            mock_repo = AsyncMock(spec=ResumeRepository)
            primary_resume = MagicMock(spec=Resume)
            primary_resume.parsed_data = sample_parsed_resume.model_dump(mode="json")
            mock_repo.get_primary_by_candidate.return_value = primary_resume
            mock_repo_class.return_value = mock_repo

            # Execute
            result = await service.recommend_jobs_for_candidate(
                candidate_id=candidate_id,
                limit=10,
                session=mock_session,
                actor_user=MagicMock(),
            )

        # Assertions
        assert embed_call_count == 1, (
            f"embed_resume() should be called exactly once during self-healing, "
            f"but was called {embed_call_count} times"
        )
        assert reindex_called_with_vector, (
            "_reindex_resume() should be called with a pre-computed vector "
            "to avoid double embedding"
        )
        assert len(result) == 1
        assert result[0].match_result.overall_score == 85.0

    @pytest.mark.asyncio
    async def test_recommend_jobs_missing_vector_no_primary_resume_raises_entity_not_found(
        self, ai_service_with_context_resolver, mock_dependencies, mock_session
    ):
        """Test graceful error when both Qdrant vector and primary resume are missing.

        Verifies:
        1. EntityNotFoundException is raised with user-friendly message
        2. No internal UUID or Qdrant details are exposed
        """
        service, context_resolver = ai_service_with_context_resolver
        candidate_id = uuid.uuid4()

        # Setup: Qdrant returns None (missing vector)
        mock_dependencies["vector_repository"].retrieve_vector.return_value = None

        # Mock ResumeRepository to return NO primary resume
        with patch("app.services.ai_matching_service.ResumeRepository") as mock_repo_class:
            mock_repo = AsyncMock(spec=ResumeRepository)
            mock_repo.get_primary_by_candidate.return_value = None
            mock_repo_class.return_value = mock_repo

            # Execute and verify exception
            with pytest.raises(EntityNotFoundException) as exc_info:
                await service.recommend_jobs_for_candidate(
                    candidate_id=candidate_id,
                    limit=10,
                    session=mock_session,
                    actor_user=MagicMock(),
                )

        # Verify user-friendly message
        error_message = str(exc_info.value)
        assert "số hoá" in error_message.lower() or "digitized" in error_message.lower()
        assert "CV" in error_message or "cv" in error_message.lower()
        # Verify no internal details exposed
        assert str(candidate_id) not in error_message
        assert "Qdrant" not in error_message
        assert "vector" not in error_message.lower()

    @pytest.mark.asyncio
    async def test_recommend_jobs_existing_vector_no_re_embed(
        self, ai_service_with_context_resolver, mock_dependencies, mock_session, sample_parsed_resume, sample_job_data
    ):
        """Test that existing Qdrant vector is used without re-embedding.

        Verifies:
        1. embed_resume() is NOT called when vector exists in Qdrant
        2. _reindex_resume() is NOT called
        3. Recommendation proceeds normally
        """
        service, context_resolver = ai_service_with_context_resolver
        candidate_id = uuid.uuid4()
        existing_vector = [0.1] * 384
        job_id_1 = sample_job_data[0][0]

        # Mock search_similar to return job results
        mock_dependencies["vector_repository"].search_similar.return_value = [
            {
                "id": str(job_id_1),
                "vector": [0.2] * 384,
                "payload": {"job_id": str(job_id_1)},
                "score": 0.85,
            }
        ]

        # Setup: Qdrant returns existing vector
        mock_dependencies["vector_repository"].retrieve_vector.return_value = {
            "vector": existing_vector,
            "payload": {"skills": sample_parsed_resume.skills},
        }

        # Update context resolver with this candidate's resume
        context_resolver.resolve_resumes = AsyncMock(
            return_value={candidate_id: sample_parsed_resume}
        )
        context_resolver.resolve_jobs = AsyncMock(
            return_value={job_id_1: sample_job_data[0][1]}
        )

        # Setup: Matching engine returns valid result
        match_result = MatchResultSchema(
            entity_id=sample_job_data[0][0],
            overall_score=85.0,
            cosine_similarity=0.85,
            skill_coverage_score=0.8,
            experience_match_score=0.8,
            matching_skills=["Python", "FastAPI"],
            skill_gap=[],
        )
        mock_dependencies["matching_engine"].match_resume_to_job.return_value = match_result

        # Track embed_resume calls
        embed_call_count = 0

        async def tracking_embed(*args, **kwargs):
            nonlocal embed_call_count
            embed_call_count += 1
            return [0.2] * 384  # Different vector to detect if called

        mock_dependencies["embedding_service"].embed_resume = tracking_embed

        # Track _reindex_resume calls
        reindex_call_count = 0

        async def tracking_reindex(*args, **kwargs):
            nonlocal reindex_call_count
            reindex_call_count += 1
            return None

        service._reindex_resume = tracking_reindex

        # Execute
        result = await service.recommend_jobs_for_candidate(
            candidate_id=candidate_id,
            limit=10,
            session=mock_session,
            actor_user=MagicMock(),
        )

        # Assertions
        assert embed_call_count == 0, (
            f"embed_resume() should NOT be called when vector exists in Qdrant, "
            f"but was called {embed_call_count} times"
        )
        assert reindex_call_count == 0, (
            f"_reindex_resume() should NOT be called when vector exists in Qdrant, "
            f"but was called {reindex_call_count} times"
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_recommend_candidates_missing_job_vector_raises_entity_not_found(
        self, ai_service_with_context_resolver, mock_dependencies, mock_session, sample_job_data
    ):
        """Test graceful error when job vector is missing from Qdrant.

        Verifies:
        1. EntityNotFoundException is raised for missing job vector
        """
        service, context_resolver = ai_service_with_context_resolver
        job_id = uuid.uuid4()

        # Setup: Qdrant returns None for job vector
        mock_dependencies["vector_repository"].retrieve_vector.return_value = None

        # Setup: Job resolver returns empty for this job_id
        context_resolver.resolve_jobs = AsyncMock(return_value={})

        with pytest.raises(EntityNotFoundException) as exc_info:
            await service.recommend_candidates_for_job(
                job_id=job_id,
                parsed_job=None,
                limit=10,
                session=mock_session,
                actor_user=MagicMock(),
            )

        error_message = str(exc_info.value)
        assert "job" in error_message.lower() or "Job" in error_message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])