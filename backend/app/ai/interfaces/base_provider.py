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
    async def search_similar(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search similar vectors by Cosine distance."""
        pass
