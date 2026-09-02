from __future__ import annotations

import asyncio
import threading
from typing import Any

from app.ai.interfaces.base_provider import BaseEmbeddingProvider
from app.core.config import settings
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema


# Module-level singleton for SentenceTransformer model (lazy, thread-safe)
_sentence_transformer_model: Any = None
_sentence_transformer_model_lock = threading.Lock()


def _get_shared_sentence_transformer_model(model_name: str | None = None) -> Any:
    """Get the shared SentenceTransformer model instance (lazy, thread-safe singleton).

    This function ensures the SentenceTransformer model is initialized exactly once
    per process, even under concurrent access.

    Args:
        model_name: The model name to load. Defaults to settings.EMBEDDING_MODEL_NAME.

    Returns:
        The shared SentenceTransformer model instance.

    Raises:
        InvalidDocumentError: If sentence-transformers is not installed or model loading fails.
    """
    global _sentence_transformer_model

    model_name = model_name or settings.EMBEDDING_MODEL_NAME

    # Fast path: already initialized
    if _sentence_transformer_model is not None:
        return _sentence_transformer_model

    # Slow path: need to initialize (with lock for thread safety)
    with _sentence_transformer_model_lock:
        # Double-check after acquiring lock
        if _sentence_transformer_model is not None:
            return _sentence_transformer_model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise InvalidDocumentError(
                f"sentence-transformers is not installed: {exc}"
            ) from exc

        try:
            _sentence_transformer_model = SentenceTransformer(model_name)
        except Exception as exc:
            raise InvalidDocumentError(
                f"Failed to load SentenceTransformer model '{model_name}': {exc}"
            ) from exc

    return _sentence_transformer_model


def _reset_sentence_transformer_model_for_testing() -> None:
    """Reset the shared model for testing purposes.

    WARNING: Only use in tests. Not thread-safe for production use.
    """
    global _sentence_transformer_model
    with _sentence_transformer_model_lock:
        _sentence_transformer_model = None


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """SentenceTransformers embedding provider.

    The underlying SentenceTransformer model is shared across all instances
    via a module-level thread-safe singleton. Model is loaded lazily on first use.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME

    def _get_model(self) -> Any:
        """Get the shared SentenceTransformer model instance."""
        return _get_shared_sentence_transformer_model(self.model_name)

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text, offloaded to thread pool."""

        def _encode():
            model = self._get_model()
            vector = model.encode(text)
            return [float(value) for value in vector]

        return await asyncio.to_thread(_encode)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts, offloaded to thread pool."""

        def _encode_batch():
            model = self._get_model()
            vectors = model.encode(texts)
            return [
                [float(value) for value in vector]
                for vector in vectors
            ]

        return await asyncio.to_thread(_encode_batch)

    # Sync versions for backward compatibility
    def embed_text_sync(self, text: str) -> list[float]:
        """Synchronous version for backward compatibility."""
        model = self._get_model()
        vector = model.encode(text)
        return [float(value) for value in vector]

    def embed_documents_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous version for backward compatibility."""
        model = self._get_model()
        vectors = model.encode(texts)
        return [
            [float(value) for value in vector]
            for vector in vectors
        ]


class EmbeddingService:
    """Orchestrates text formatting and delegates to an embedding provider."""

    def __init__(self, provider: BaseEmbeddingProvider) -> None:
        self.provider = provider

    async def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise EmptyDocumentError(
                "Text for embedding generation cannot be empty"
            )
        try:
            return await self.provider.embed_text(text)
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise InvalidDocumentError(
                "Failed to generate embedding vector"
            ) from exc

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return await self.provider.embed_documents(texts)
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise InvalidDocumentError(
                "Failed to generate embedding vectors"
            ) from exc

    @staticmethod
    def _format_resume_text(resume: ParsedResumeSchema) -> str:
        parts = []

        if resume.title:
            parts.append(f"Title: {resume.title}")

        if resume.summary:
            parts.append(f"Summary: {resume.summary}")

        if resume.skills:
            parts.append(f"Skills: {', '.join(resume.skills)}")

        if resume.experiences:
            exp_texts = [
                f"{e.position} at {e.company}: {e.description or ''}"
                for e in resume.experiences
                if e.position or e.company
            ]
            if exp_texts:
                parts.append(f"Experiences: {'; '.join(exp_texts)}")

        return " | ".join(parts) if parts else "Candidate Profile"

    async def embed_resume(self, parsed_resume: ParsedResumeSchema) -> list[float]:
        text = self._format_resume_text(parsed_resume)
        return await self.embed_text(text)

    @staticmethod
    def _format_job_text(job: ParsedJobSchema) -> str:
        parts = []

        if job.title:
            parts.append(f"Job Title: {job.title}")

        if job.summary:
            parts.append(f"Summary: {job.summary}")

        if job.required_skills:
            parts.append(f"Required Skills: {', '.join(job.required_skills)}")

        if job.preferred_skills:
            parts.append(
                f"Preferred Skills: {', '.join(job.preferred_skills)}"
            )

        return " | ".join(parts) if parts else "Job Description"

    async def embed_job(self, parsed_job: ParsedJobSchema) -> list[float]:
        text = self._format_job_text(parsed_job)
        return await self.embed_text(text)