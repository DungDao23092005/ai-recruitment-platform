from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_search import SemanticSearchResult
from app.services.semantic_search_service import SemanticSearchService


def make_embedding_service(query_vector=None):
    svc = MagicMock()
    svc.embed_text = MagicMock(return_value=query_vector or [0.1, 0.2, 0.3])
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
