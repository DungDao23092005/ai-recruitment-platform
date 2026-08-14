from __future__ import annotations

from typing import Any

from app.ai.embeddings.embedding_service import EmbeddingService
from app.ai.interfaces.base_provider import BaseVectorRepository
from app.core.exceptions import (
    AIError,
    EmptyDocumentError,
    InvalidDocumentError,
)
from app.schemas.ai_search import SemanticSearchResult


class SemanticSearchService:
    """Semantic search over indexed jobs and candidate resumes.

    Natural language query -> embedding -> vector search -> typed results.
    The semantic score is preserved exactly as returned by the vector store.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_repository: BaseVectorRepository | None = None,
    ) -> None:
        from app.ai.vector_db.qdrant_client import QdrantVectorRepository
        from app.ai.embeddings.embedding_service import (
            SentenceTransformerEmbeddingProvider,
        )

        self.embedding_service = embedding_service or EmbeddingService(
            SentenceTransformerEmbeddingProvider()
        )
        self.vector_repository = vector_repository or QdrantVectorRepository()

    async def search_jobs(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[SemanticSearchResult]:
        return await self._search(
            collection_name="jobs",
            id_field="job_id",
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )

    async def search_candidates(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[SemanticSearchResult]:
        return await self._search(
            collection_name="resumes",
            id_field="candidate_id",
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )

    async def _search(
        self,
        collection_name: str,
        id_field: str,
        query: str,
        limit: int,
        score_threshold: float | None,
    ) -> list[SemanticSearchResult]:
        effective_limit = max(1, min(100, limit))

        if not query or not query.strip():
            raise EmptyDocumentError(
                "Search query cannot be empty"
            )

        query_vector = self.embedding_service.embed_text(query)

        try:
            raw_results = await self.vector_repository.search_similar(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=effective_limit,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(
                f"Failed to search similar vectors in collection "
                f"'{collection_name}'"
            ) from exc

        results: list[SemanticSearchResult] = []
        for res in raw_results:
            point_id = self._extract_point_id(res, id_field)
            if point_id is None:
                continue
            score = self._extract_score(res)
            if score is None:
                continue
            if score_threshold is not None and score < score_threshold:
                continue
            payload = res.get("payload") or {}
            results.append(
                SemanticSearchResult(
                    id=point_id,
                    score=score,
                    skills=list(payload.get("skills") or []),
                    created_at=payload.get("created_at"),
                )
            )
        return results

    @staticmethod
    def _extract_point_id(res: dict[str, Any], id_field: str) -> str | None:
        raw_id = res.get("id") or (res.get("payload") or {}).get(id_field)
        if raw_id is None:
            return None
        return str(raw_id)

    @staticmethod
    def _extract_score(res: dict[str, Any]) -> float | None:
        raw_score = res.get("score")
        if raw_score is None:
            return None
        try:
            return float(raw_score)
        except (TypeError, ValueError):
            return None