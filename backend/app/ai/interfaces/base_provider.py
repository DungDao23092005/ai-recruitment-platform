from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, TypeVar

T = TypeVar("T")


class BaseLLMProvider(ABC):
    """Abstract interface for LLM operations (e.g. Gemini)."""

    @abstractmethod
    async def generate_structured_output(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
    ) -> T:
        """Generate structured output adhering to a Pydantic schema."""
        pass


class BaseEmbeddingProvider(ABC):
    """Abstract interface for Vector Embedding generation."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate vector embedding for a single text string."""
        pass

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of text strings."""
        pass


class BaseVectorRepository(ABC):
    """Abstract interface for Vector DB operations (e.g. Qdrant)."""

    @abstractmethod
    async def upsert_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Upsert a vector point with metadata payload."""
        pass

    @abstractmethod
    async def delete_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
    ) -> None:
        """Delete a vector point by ID."""
        pass

    @abstractmethod
    async def retrieve_vector(
        self,
        collection_name: str,
        point_id: str | uuid.UUID,
    ) -> dict[str, Any] | None:
        """Retrieve a vector point by ID together with vector data
        and payload metadata.

        Returns:
            A dict of the form ``{"id": str, "vector": list[float],
            "payload": dict}`` when the point exists, or ``None`` when
            it does not.
        """
        pass

    @abstractmethod
    async def search_similar(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search similar vectors by Cosine distance.

        Args:
            collection_name: Name of the collection to search.
            query_vector: Query vector for similarity search.
            limit: Maximum number of results to return.
            filters: Optional metadata filters.
            score_threshold: Minimum similarity score threshold (0.0 to 1.0).
                           Results below this threshold are filtered out.
        """
        pass


class RerankCandidate:
    """Represents an authorized entity for reranking."""

    def __init__(
        self,
        entity_id: uuid.UUID,
        source_type: str,
        title: str,
        text_for_reranking: str,
        original_relevance_score: float,
    ) -> None:
        self.entity_id = entity_id
        self.source_type = source_type
        self.title = title
        self.text_for_reranking = text_for_reranking
        self.original_relevance_score = original_relevance_score


class RerankResult:
    """Result of reranking a candidate."""

    def __init__(
        self,
        entity_id: uuid.UUID,
        rerank_score: float,
    ) -> None:
        self.entity_id = entity_id
        self.rerank_score = rerank_score


class BaseReranker(ABC):
    """Abstract interface for semantic reranking of authorized entities.

    The reranker receives ONLY entities that have passed ContextResolver
    authorization and SQL hydration. It must NOT access SQL, Qdrant, or
    ContextResolver directly.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankResult]:
        """Rerank authorized candidates against the query.

        Args:
            query: The standalone query for retrieval.
            candidates: List of authorized, SQL-hydrated entities with text for reranking.

        Returns:
            List of RerankResult with entity_id and rerank_score, sorted by score descending.
        """
        pass
