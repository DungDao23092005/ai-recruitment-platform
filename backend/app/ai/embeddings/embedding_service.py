from __future__ import annotations

from app.ai.interfaces.base_provider import BaseEmbeddingProvider
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.core.config import settings
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """SentenceTransformers embedding provider.

    The underlying SentenceTransformer model is loaded lazily: instantiating
    this provider never triggers a model download; the model is created only
    when an embedding is actually requested.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.model = None

    def _get_model(self):
        """Load the SentenceTransformer model on first use."""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise InvalidDocumentError(
                    f"sentence-transformers is not installed: {exc}"
                ) from exc
            self.model = SentenceTransformer(self.model_name)
        return self.model

    def embed_text(self, text: str) -> list[float]:
        model = self._get_model()
        vector = model.encode(text)
        return [float(value) for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
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

    def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise EmptyDocumentError(
                "Text for embedding generation cannot be empty"
            )
        try:
            return self.provider.embed_text(text)
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise InvalidDocumentError(
                "Failed to generate embedding vector"
            ) from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return self.provider.embed_documents(texts)
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

    def embed_resume(self, parsed_resume: ParsedResumeSchema) -> list[float]:
        text = self._format_resume_text(parsed_resume)
        return self.embed_text(text)

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

    def embed_job(self, parsed_job: ParsedJobSchema) -> list[float]:
        text = self._format_job_text(parsed_job)
        return self.embed_text(text)