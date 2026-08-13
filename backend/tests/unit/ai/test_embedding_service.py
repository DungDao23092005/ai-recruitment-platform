from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from app.ai.embeddings.embedding_service import (
    EmbeddingService,
    SentenceTransformerEmbeddingProvider,
)
from app.ai.interfaces.base_provider import BaseEmbeddingProvider
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import (
    EducationSchema,
    ParsedResumeSchema,
    WorkExperienceSchema,
)

MOCK_VECTOR_384 = [0.1] * 384


def make_mock_provider() -> MagicMock:
    return MagicMock(spec=BaseEmbeddingProvider)


@pytest.fixture
def fake_sentence_transformer(monkeypatch):
    """Inject a fake sentence_transformers module so tests stay offline.

    The provider imports SentenceTransformer lazily inside _get_model();
    stubbing sys.modules guarantees no real model download or torch import.
    """
    fake_module = types.ModuleType("sentence_transformers")
    fake_cls = MagicMock()
    fake_module.SentenceTransformer = fake_cls
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    return fake_cls


def make_resume() -> ParsedResumeSchema:
    return ParsedResumeSchema(
        full_name="Nguyen Van A",
        title="Senior Python Developer",
        summary="Experienced Python backend developer.",
        skills=["Python", "FastAPI"],
        experiences=[
            WorkExperienceSchema(
                company="Tech Corp",
                position="Senior Python Developer",
                description="Lead backend team",
                start_date="01/2021",
                end_date="Present",
                is_current=True,
            )
        ],
        education=[
            EducationSchema(
                institution="HUST",
                degree="Bachelor",
                field_of_study="Computer Science",
                start_year=2016,
                end_year=2020,
            )
        ],
    )


def make_job() -> ParsedJobSchema:
    return ParsedJobSchema(
        title="Backend Engineer",
        summary="Build backend services.",
        required_skills=["Python", "FastAPI"],
        preferred_skills=["Docker"],
        minimum_years_experience=3.0,
        education_level="Bachelor",
    )


class TestEmbeddingService:
    def test_embed_text_success(self):
        provider = make_mock_provider()
        provider.embed_text.return_value = MOCK_VECTOR_384
        service = EmbeddingService(provider)

        vector = service.embed_text("text")

        assert vector == MOCK_VECTOR_384
        assert len(vector) == 384
        provider.embed_text.assert_called_once_with("text")

    @pytest.mark.parametrize("bad_text", ["", " ", "\n", "  \n\t  "])
    def test_embed_text_empty_raises_empty_document_error(self, bad_text):
        provider = make_mock_provider()
        service = EmbeddingService(provider)

        with pytest.raises(EmptyDocumentError):
            service.embed_text(bad_text)

        provider.embed_text.assert_not_called()

    def test_embed_documents_batch(self):
        provider = make_mock_provider()
        provider.embed_documents.return_value = [MOCK_VECTOR_384, MOCK_VECTOR_384]
        service = EmbeddingService(provider)
        texts = ["python", "fastapi"]

        vectors = service.embed_documents(texts)

        assert len(vectors) == 2
        assert all(len(v) == 384 for v in vectors)
        provider.embed_documents.assert_called_once_with(texts)

    def test_embed_documents_empty_returns_empty_list(self):
        provider = make_mock_provider()
        service = EmbeddingService(provider)

        result = service.embed_documents([])

        assert result == []
        provider.embed_documents.assert_not_called()

    def test_embed_resume_formatting(self):
        provider = make_mock_provider()
        provider.embed_text.return_value = MOCK_VECTOR_384
        service = EmbeddingService(provider)
        resume = make_resume()

        vector = service.embed_resume(resume)

        assert vector == MOCK_VECTOR_384
        formatted = provider.embed_text.call_args.args[0]
        assert "Title: Senior Python Developer" in formatted
        assert "Summary: Experienced Python backend developer." in formatted
        assert "Skills: Python, FastAPI" in formatted
        assert "Experiences:" in formatted
        assert "Senior Python Developer at Tech Corp: Lead backend team" in formatted

    def test_embed_job_formatting(self):
        provider = make_mock_provider()
        provider.embed_text.return_value = MOCK_VECTOR_384
        service = EmbeddingService(provider)
        job = make_job()

        vector = service.embed_job(job)

        assert vector == MOCK_VECTOR_384
        formatted = provider.embed_text.call_args.args[0]
        assert "Job Title: Backend Engineer" in formatted
        assert "Summary: Build backend services." in formatted
        assert "Required Skills: Python, FastAPI" in formatted
        assert "Preferred Skills: Docker" in formatted

    def test_provider_failure_maps_to_invalid_document_error(self):
        provider = make_mock_provider()
        provider.embed_text.side_effect = RuntimeError("boom")
        service = EmbeddingService(provider)

        with pytest.raises(InvalidDocumentError):
            service.embed_text("text")

        error_message = None
        try:
            service.embed_text("text")
        except InvalidDocumentError as exc:
            error_message = str(exc)
        assert "boom" not in (error_message or "")
        assert "GEMINI_API_KEY" not in (error_message or "")


class TestSentenceTransformerEmbeddingProvider:
    def test_lazy_load(self, fake_sentence_transformer):
        provider = SentenceTransformerEmbeddingProvider()

        fake_sentence_transformer.assert_not_called()
        assert provider.model is None

        provider.embed_text("hello")

        fake_sentence_transformer.assert_called_once_with(provider.model_name)
        mock_model = fake_sentence_transformer.return_value
        mock_model.encode.assert_called_once_with("hello")

    def test_embed_text(self, fake_sentence_transformer):
        mock_model = fake_sentence_transformer.return_value
        mock_model.encode.return_value = MOCK_VECTOR_384
        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        vector = provider.embed_text("hello")

        mock_model.encode.assert_called_once_with("hello")
        assert len(vector) == 384
        assert all(isinstance(v, float) for v in vector)

    def test_embed_documents(self, fake_sentence_transformer):
        mock_model = fake_sentence_transformer.return_value
        mock_model.encode.return_value = [MOCK_VECTOR_384, MOCK_VECTOR_384]
        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        vectors = provider.embed_documents(["a", "b"])

        mock_model.encode.assert_called_once_with(["a", "b"])
        assert len(vectors) == 2
        assert all(len(v) == 384 for v in vectors)
