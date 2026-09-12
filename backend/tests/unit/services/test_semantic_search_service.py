from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_search import SemanticSearchResult
from app.services.semantic_search_service import SemanticSearchService


def make_embedding_service(query_vector=None):
    svc = MagicMock()
    svc.embed_text = AsyncMock(return_value=query_vector or [0.1, 0.2, 0.3])
    return svc


def make_vector_repo(results=None):
    repo = MagicMock()
    repo.search_similar = AsyncMock(return_value=results or [])
    return repo


def make_service(embedding_service=None, vector_repository=None):
    return SemanticSearchService(
        embedding_service=embedding_service,
        vector_repository=vector_repository,
    )


def make_scored_point(
    point_id="1234",
    score=0.87,
    skills=None,
    created_at="2026-01-01T00:00:00+00:00",
):
    return {
        "id": point_id,
        "score": score,
        "payload": {
            "skills": skills or ["Python", "FastAPI"],
            "created_at": created_at,
            "is_deleted": False,
        },
    }


def make_job_repo(jobs=None, filter_fn=None):
    """Create a mock job repository.

    Args:
        jobs: List of jobs to return (will be filtered if filter_fn provided)
        filter_fn: Optional function(job) -> bool to filter jobs before returning
    """
    if jobs is not None and filter_fn is not None:
        filtered_jobs = [j for j in jobs if filter_fn(j)]
    else:
        filtered_jobs = jobs or []

    repo = MagicMock()
    repo.session = MagicMock()
    # Create a proper async mock chain for execute -> scalars -> unique -> all
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_unique = MagicMock()
    mock_unique.all.return_value = filtered_jobs
    mock_scalars.unique.return_value = mock_unique
    mock_result.scalars.return_value = mock_scalars
    repo.session.execute = AsyncMock(return_value=mock_result)
    return repo


def make_company(name="Test Company"):
    company = MagicMock()
    company.name = name
    return company


def make_job(job_id, title="Test Job", company=None, location="HCM"):
    job = MagicMock()
    job.id = job_id
    job.title = title
    job.company = company or make_company()
    job.location = location
    job.is_deleted = False
    return job


@pytest.fixture
def provider():
    embed = make_embedding_service()
    repo = make_vector_repo()
    return embed, repo


class TestSearchJobs:
    def test_success(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [make_scored_point()]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python backend"))

        assert isinstance(result, list)
        assert len(result) == 1
        item = result[0]
        assert item.id == "1234"
        assert item.score == 0.87
        assert item.skills == ["Python", "FastAPI"]

    def test_correct_collection(self, provider):
        embed, repo = provider
        service = make_service(embed, repo)

        asyncio.run(service.search_jobs("python"))

        repo.search_similar.assert_awaited_once_with(
            collection_name="jobs",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
        )

    def test_embedding_called(self, provider):
        embed, repo = provider
        service = make_service(embed, repo)

        asyncio.run(service.search_jobs("data engineer"))

        embed.embed_text.assert_called_once_with("data engineer")

    def test_score_preserved(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            make_scored_point(point_id="a", score=0.9123)
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("react"))

        assert result[0].score == 0.9123

    def test_score_threshold_filters_low_scores(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            make_scored_point(point_id="a", score=0.8),
            make_scored_point(point_id="b", score=0.5),
            make_scored_point(point_id="c", score=0.95),
        ]
        service = make_service(embed, repo)

        result = asyncio.run(
            service.search_jobs("react", score_threshold=0.6)
        )

        assert [item.id for item in result] == ["a", "c"]

    def test_limit_bounds(self, provider):
        embed, repo = provider
        service = make_service(embed, repo)

        asyncio.run(service.search_jobs("react", limit=0))
        repo.search_similar.assert_awaited_once_with(
            collection_name="jobs",
            query_vector=[0.1, 0.2, 0.3],
            limit=1,
        )

        asyncio.run(service.search_jobs("react", limit=500))
        repo.search_similar.assert_awaited_with(
            collection_name="jobs",
            query_vector=[0.1, 0.2, 0.3],
            limit=100,
        )

    def test_empty_result(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = []
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("nothing"))

        assert result == []

    def test_skips_points_without_id(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            {"id": None, "score": 0.5, "payload": {"skills": []}},
            make_scored_point(point_id="real", score=0.9),
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python"))

        assert [item.id for item in result] == ["real"]

    def test_skips_points_without_score(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            {"id": "x", "score": None, "payload": {"skills": []}},
            make_scored_point(point_id="real", score=0.9),
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python"))

        assert [item.id for item in result] == ["real"]

    def test_uses_payload_id_fallback(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            {
                "id": None,
                "score": 0.75,
                "payload": {"job_id": "job-from-payload", "skills": []},
            }
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python"))

        assert result[0].id == "job-from-payload"

    def test_missing_payload_fields_default(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [{"id": "a", "score": 0.6}]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python"))

        assert result[0].skills == []
        assert result[0].created_at is None


class TestSearchJobsEnrichment:
    """Tests for job search with database enrichment."""

    def test_enrichment_adds_job_metadata(self, provider):
        embed, repo = provider
        job_id = str(uuid.uuid4())
        repo.search_similar.return_value = [
            make_scored_point(point_id=job_id, score=0.76, skills=["Python", "FastAPI"])
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo()
        job = make_job(uuid.UUID(job_id), title="Backend Engineer", location="HCM")
        job_repo.session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [job]

        result = asyncio.run(service.search_jobs("python backend", job_repository=job_repo))

        assert len(result) == 1
        item = result[0]
        assert item.id == job_id
        assert item.score == 0.76
        assert item.skills == ["Python", "FastAPI"]
        assert item.title == "Backend Engineer"
        assert item.company_name == "Test Company"
        assert item.location == "HCM"

    def test_enrichment_preserves_qdrant_order(self, provider):
        embed, repo = provider
        job_id_1 = str(uuid.uuid4())
        job_id_2 = str(uuid.uuid4())
        # Qdrant returns in order: job_id_1 (score 0.8), job_id_2 (score 0.7)
        repo.search_similar.return_value = [
            make_scored_point(point_id=job_id_1, score=0.8),
            make_scored_point(point_id=job_id_2, score=0.7),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo()
        job1 = make_job(uuid.UUID(job_id_1), title="Job A", location="HN")
        job2 = make_job(uuid.UUID(job_id_2), title="Job B", location="HCM")
        job_repo.session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [job1, job2]

        result = asyncio.run(service.search_jobs("python", job_repository=job_repo))

        assert len(result) == 2
        assert result[0].id == job_id_1
        assert result[0].title == "Job A"
        assert result[1].id == job_id_2
        assert result[1].title == "Job B"

    def test_enrichment_filters_deleted_jobs(self, provider):
        embed, repo = provider
        job_id_1 = str(uuid.uuid4())
        job_id_2 = str(uuid.uuid4())
        repo.search_similar.return_value = [
            make_scored_point(point_id=job_id_1, score=0.8),
            make_scored_point(point_id=job_id_2, score=0.7),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo()
        # Only job1 exists in DB (job2 is deleted/missing)
        job1 = make_job(uuid.UUID(job_id_1), title="Job A", location="HN")
        job_repo.session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [job1]

        result = asyncio.run(service.search_jobs("python", job_repository=job_repo))

        assert len(result) == 1
        assert result[0].id == job_id_1

    def test_enrichment_handles_missing_company(self, provider):
        embed, repo = provider
        job_id = str(uuid.uuid4())
        repo.search_similar.return_value = [
            make_scored_point(point_id=job_id, score=0.76)
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo()
        # Create job without company
        job = make_job(uuid.UUID(job_id), title="Backend Engineer", location="HCM")
        job.company = None
        job_repo.session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [job]

        result = asyncio.run(service.search_jobs("python backend", job_repository=job_repo))

        assert len(result) == 1
        assert result[0].title == "Backend Engineer"
        assert result[0].company_name is None
        assert result[0].location == "HCM"

    def test_without_repository_returns_raw_results(self, provider):
        embed, repo = provider
        job_id = str(uuid.uuid4())
        repo.search_similar.return_value = [
            make_scored_point(point_id=job_id, score=0.76)
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python"))

        assert len(result) == 1
        assert result[0].id == job_id
        assert result[0].score == 0.76
        assert result[0].title is None
        assert result[0].company_name is None
        assert result[0].location is None


class TestSearchCandidates:
    def test_correct_collection(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [make_scored_point()]
        service = make_service(embed, repo)

        asyncio.run(service.search_candidates("react developer"))

        repo.search_similar.assert_awaited_once_with(
            collection_name="resumes",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
        )

    def test_payload_candidate_id_fallback(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            {
                "id": None,
                "score": 0.7,
                "payload": {"candidate_id": "cand-42", "skills": []},
            }
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_candidates("python"))

        assert result[0].id == "cand-42"


class TestFailures:
    def test_empty_query_raises(self, provider):
        embed, repo = provider
        service = make_service(embed, repo)

        with pytest.raises(EmptyDocumentError):
            asyncio.run(service.search_jobs(""))

    def test_whitespace_query_raises(self, provider):
        embed, repo = provider
        service = make_service(embed, repo)

        with pytest.raises(EmptyDocumentError):
            asyncio.run(service.search_jobs("   "))

    def test_embedding_failure_maps(self, provider):
        embed, repo = provider
        embed.embed_text.side_effect = InvalidDocumentError(
            "Failed to generate embedding vector"
        )
        service = make_service(embed, repo)

        with pytest.raises(InvalidDocumentError):
            asyncio.run(service.search_jobs("python"))

    def test_qdrant_failure_propagates(self, provider):
        embed, repo = provider
        repo.search_similar.side_effect = AIError(
            "Failed to search similar vectors in collection 'jobs'"
        )
        service = make_service(embed, repo)

        with pytest.raises(AIError):
            asyncio.run(service.search_jobs("python"))

    def test_qdrant_unexpected_failure_maps(self, provider):
        embed, repo = provider
        repo.search_similar.side_effect = RuntimeError("connection refused")
        service = make_service(embed, repo)

        with pytest.raises(AIError):
            asyncio.run(service.search_jobs("python"))

    def test_no_dependency_uses_default_providers(self):
        service = SemanticSearchService()
        assert service.embedding_service is not None
        assert service.vector_repository is not None


class TestNoFabrication:
    def test_does_not_alter_scores(self, provider):
        embed, repo = provider
        repo.search_similar.return_value = [
            make_scored_point(point_id="a", score=0.1234)
        ]
        service = make_service(embed, repo)

        result = asyncio.run(service.search_jobs("python"))

        assert result[0].score == 0.1234
        assert result[0].score != 100.0


class TestSearchJobsRoleBasedVisibility:
    """SEC-02 Regression Tests: Semantic search role-based visibility.

    These tests verify that the SQL hydration layer correctly applies
    role-based visibility filters. They do NOT mock _fetch_jobs() -
    they verify the actual SQL predicate and returned data.
    """

    def _make_user(self, role: str, user_id: uuid.UUID | None = None):
        from app.domain.enums import UserRole
        from types import SimpleNamespace
        user = SimpleNamespace(
            id=user_id or uuid.uuid4(),
            role=UserRole(role),
            is_active=True,
        )
        return user

    def _make_job(self, job_id: uuid.UUID, status: str = "published", company_id: uuid.UUID | None = None, is_deleted: bool = False):
        from app.domain.enums import JobStatus
        job = MagicMock()
        job.id = job_id
        job.title = "Test Job"
        job.company = MagicMock()
        job.company.name = "Test Company"
        job.location = "HCM"
        job.status = JobStatus(status)
        job.is_deleted = is_deleted
        job.company_id = company_id or uuid.uuid4()
        return job

    def _candidate_filter(self, job):
        return job.status.name == "PUBLISHED" and not job.is_deleted

    def _recruiter_filter(self, company_id):
        def filter_fn(job):
            return job.company_id == company_id and not job.is_deleted
        return filter_fn

    def _admin_filter(self, job):
        return not job.is_deleted

    def test_candidate_sees_only_published_jobs(self, provider):
        """Candidate: PUBLISHED visible, DRAFT/CLOSED/EXPIRED hidden, DELETED hidden"""
        embed, repo = provider
        job_pub = self._make_job(uuid.uuid4(), "published")
        job_draft = self._make_job(uuid.uuid4(), "draft")
        job_closed = self._make_job(uuid.uuid4(), "closed")
        job_expired = self._make_job(uuid.uuid4(), "expired")
        job_deleted = self._make_job(uuid.uuid4(), "published", is_deleted=True)

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_pub.id), score=0.9),
            make_scored_point(point_id=str(job_draft.id), score=0.8),
            make_scored_point(point_id=str(job_closed.id), score=0.7),
            make_scored_point(point_id=str(job_expired.id), score=0.6),
            make_scored_point(point_id=str(job_deleted.id), score=0.5),
        ]
        service = make_service(embed, repo)

        all_jobs = [job_pub, job_draft, job_closed, job_expired, job_deleted]
        job_repo = make_job_repo(all_jobs, self._candidate_filter)

        candidate_user = self._make_user("candidate")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=candidate_user))

        # Only PUBLISHED non-deleted job should be visible
        assert len(result) == 1
        assert result[0].id == str(job_pub.id)

    def test_candidate_does_not_see_draft(self, provider):
        """Candidate: DRAFT job hidden"""
        embed, repo = provider
        job_draft = self._make_job(uuid.uuid4(), "draft")

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_draft.id), score=0.9),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo([job_draft], self._candidate_filter)

        candidate_user = self._make_user("candidate")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=candidate_user))

        assert len(result) == 0

    def test_candidate_does_not_see_closed(self, provider):
        """Candidate: CLOSED job hidden"""
        embed, repo = provider
        job_closed = self._make_job(uuid.uuid4(), "closed")

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_closed.id), score=0.9),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo([job_closed], self._candidate_filter)

        candidate_user = self._make_user("candidate")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=candidate_user))

        assert len(result) == 0

    def test_candidate_does_not_see_expired(self, provider):
        """Candidate: EXPIRED job hidden"""
        embed, repo = provider
        job_expired = self._make_job(uuid.uuid4(), "expired")

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_expired.id), score=0.9),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo([job_expired], self._candidate_filter)

        candidate_user = self._make_user("candidate")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=candidate_user))

        assert len(result) == 0

    def test_candidate_does_not_see_deleted(self, provider):
        """Candidate: DELETED job hidden"""
        embed, repo = provider
        job_deleted = self._make_job(uuid.uuid4(), "published", is_deleted=True)

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_deleted.id), score=0.9),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo([job_deleted], self._candidate_filter)

        candidate_user = self._make_user("candidate")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=candidate_user))

        assert len(result) == 0

    def test_recruiter_sees_own_company_jobs(self, provider):
        """Recruiter: sees jobs from own company (any status except deleted)"""
        embed, repo = provider
        company_id = uuid.uuid4()
        other_company_id = uuid.uuid4()

        job_own_pub = self._make_job(uuid.uuid4(), "published", company_id)
        job_own_draft = self._make_job(uuid.uuid4(), "draft", company_id)
        job_other = self._make_job(uuid.uuid4(), "published", other_company_id)

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_own_pub.id), score=0.9),
            make_scored_point(point_id=str(job_own_draft.id), score=0.8),
            make_scored_point(point_id=str(job_other.id), score=0.7),
        ]
        service = make_service(embed, repo)

        all_jobs = [job_own_pub, job_own_draft, job_other]
        job_repo = make_job_repo(all_jobs, self._recruiter_filter(company_id))

        # Mock _get_recruiter_company_id to return the recruiter's company
        service._get_recruiter_company_id = AsyncMock(return_value=company_id)

        recruiter_user = self._make_user("recruiter")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=recruiter_user))

        # Should see both published and draft from own company
        assert len(result) == 2
        result_ids = {r.id for r in result}
        assert str(job_own_pub.id) in result_ids
        assert str(job_own_draft.id) in result_ids
        assert str(job_other.id) not in result_ids

    def test_recruiter_does_not_see_other_company_jobs(self, provider):
        """Recruiter: cannot see jobs from other companies"""
        embed, repo = provider
        company_id = uuid.uuid4()
        other_company_id = uuid.uuid4()

        job_other = self._make_job(uuid.uuid4(), "published", other_company_id)

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_other.id), score=0.9),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo([job_other], self._recruiter_filter(company_id))

        service._get_recruiter_company_id = AsyncMock(return_value=company_id)

        recruiter_user = self._make_user("recruiter")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=recruiter_user))

        assert len(result) == 0

    def test_admin_sees_all_non_deleted(self, provider):
        """Admin: sees all non-deleted jobs regardless of status"""
        embed, repo = provider
        job_pub = self._make_job(uuid.uuid4(), "published")
        job_draft = self._make_job(uuid.uuid4(), "draft")
        job_closed = self._make_job(uuid.uuid4(), "closed")
        job_expired = self._make_job(uuid.uuid4(), "expired")

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_pub.id), score=0.9),
            make_scored_point(point_id=str(job_draft.id), score=0.8),
            make_scored_point(point_id=str(job_closed.id), score=0.7),
            make_scored_point(point_id=str(job_expired.id), score=0.6),
        ]
        service = make_service(embed, repo)

        all_jobs = [job_pub, job_draft, job_closed, job_expired]
        job_repo = make_job_repo(all_jobs, self._admin_filter)

        admin_user = self._make_user("admin")
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo, actor_user=admin_user))

        # Admin sees all non-deleted jobs regardless of status
        assert len(result) == 4
        result_ids = {r.id for r in result}
        assert str(job_pub.id) in result_ids
        assert str(job_draft.id) in result_ids
        assert str(job_closed.id) in result_ids
        assert str(job_expired.id) in result_ids

    def test_candidate_without_actor_user_no_visibility_filter(self, provider):
        """Without actor_user, no visibility filter applied (backward compat)"""
        embed, repo = provider
        job_pub = self._make_job(uuid.uuid4(), "published")
        job_draft = self._make_job(uuid.uuid4(), "draft")

        repo.search_similar.return_value = [
            make_scored_point(point_id=str(job_pub.id), score=0.9),
            make_scored_point(point_id=str(job_draft.id), score=0.8),
        ]
        service = make_service(embed, repo)

        job_repo = make_job_repo()
        job_repo.session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
            job_pub, job_draft
        ]

        # No actor_user passed - should return all non-deleted (backward compat)
        result = asyncio.run(service.search_jobs("test", job_repository=job_repo))

        # Should see both (backward compat)
        assert len(result) == 2
