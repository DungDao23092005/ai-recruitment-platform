from __future__ import annotations

import asyncio
import sys
import threading
import types
from unittest.mock import AsyncMock, MagicMock, patch

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


MOCK_VECTOR_384 = [0.1] * 384


def make_mock_provider() -> MagicMock:
    return MagicMock(spec=BaseEmbeddingProvider)


class TestEmbeddingService:
    async def test_embed_text_success(self):
        provider = make_mock_provider()
        provider.embed_text.return_value = MOCK_VECTOR_384
        service = EmbeddingService(provider)

        vector = await service.embed_text("text")

        assert vector == MOCK_VECTOR_384
        assert len(vector) == 384
        provider.embed_text.assert_called_once_with("text")

    @pytest.mark.parametrize("bad_text", ["", " ", "\n", "  \n\t  "])
    async def test_embed_text_empty_raises_empty_document_error(self, bad_text):
        provider = make_mock_provider()
        service = EmbeddingService(provider)

        with pytest.raises(EmptyDocumentError):
            await service.embed_text(bad_text)

        provider.embed_text.assert_not_called()

    async def test_embed_documents_batch(self):
        provider = make_mock_provider()
        provider.embed_documents.return_value = [MOCK_VECTOR_384, MOCK_VECTOR_384]
        service = EmbeddingService(provider)
        texts = ["python", "fastapi"]

        vectors = await service.embed_documents(texts)

        assert len(vectors) == 2
        assert all(len(v) == 384 for v in vectors)
        provider.embed_documents.assert_called_once_with(texts)

    async def test_embed_documents_empty_returns_empty_list(self):
        provider = make_mock_provider()
        service = EmbeddingService(provider)

        result = await service.embed_documents([])

        assert result == []
        provider.embed_documents.assert_not_called()

    async def test_embed_resume_formatting(self):
        provider = make_mock_provider()
        provider.embed_text.return_value = MOCK_VECTOR_384
        service = EmbeddingService(provider)
        resume = make_resume()

        vector = await service.embed_resume(resume)

        assert vector == MOCK_VECTOR_384
        formatted = provider.embed_text.call_args.args[0]
        assert "Title: Senior Python Developer" in formatted
        assert "Summary: Experienced Python backend developer." in formatted
        assert "Skills: Python, FastAPI" in formatted
        assert "Experiences:" in formatted
        assert "Senior Python Developer at Tech Corp: Lead backend team" in formatted

    async def test_embed_job_formatting(self):
        provider = make_mock_provider()
        provider.embed_text.return_value = MOCK_VECTOR_384
        service = EmbeddingService(provider)
        job = make_job()

        vector = await service.embed_job(job)

        assert vector == MOCK_VECTOR_384
        formatted = provider.embed_text.call_args.args[0]
        assert "Job Title: Backend Engineer" in formatted
        assert "Summary: Build backend services." in formatted
        assert "Required Skills: Python, FastAPI" in formatted
        assert "Preferred Skills: Docker" in formatted

    async def test_provider_failure_maps_to_invalid_document_error(self):
        provider = make_mock_provider()
        provider.embed_text.side_effect = RuntimeError("boom")
        service = EmbeddingService(provider)

        with pytest.raises(InvalidDocumentError):
            await service.embed_text("text")

        error_message = None
        try:
            await service.embed_text("text")
        except InvalidDocumentError as exc:
            error_message = str(exc)
        assert "boom" not in (error_message or "")
        assert "GEMINI_API_KEY" not in (error_message or "")


class TestSentenceTransformerEmbeddingProvider:
    async def test_lazy_load(self, fake_sentence_transformer):
        from app.ai.embeddings.embedding_service import _sentence_transformer_model, _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        provider = SentenceTransformerEmbeddingProvider()

        fake_sentence_transformer.assert_not_called()
        assert _sentence_transformer_model is None

        await provider.embed_text("hello")

        fake_sentence_transformer.assert_called_once_with(provider.model_name)
        mock_model = fake_sentence_transformer.return_value
        mock_model.encode.assert_called_once_with("hello")

    async def test_embed_text(self, fake_sentence_transformer):
        from app.ai.embeddings.embedding_service import _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        mock_model = fake_sentence_transformer.return_value
        mock_model.encode.return_value = MOCK_VECTOR_384
        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        vector = await provider.embed_text("hello")

        mock_model.encode.assert_called_once_with("hello")
        assert len(vector) == 384
        assert all(isinstance(v, float) for v in vector)

    async def test_embed_documents(self, fake_sentence_transformer):
        from app.ai.embeddings.embedding_service import _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        mock_model = fake_sentence_transformer.return_value
        # model.encode returns a numpy array of shape (n_texts, dim)
        import numpy as np
        mock_model.encode.return_value = np.array([MOCK_VECTOR_384, MOCK_VECTOR_384])
        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        vectors = await provider.embed_documents(["a", "b"])

        mock_model.encode.assert_called_once_with(["a", "b"])
        assert len(vectors) == 2
        assert all(len(v) == 384 for v in vectors)

    async def test_get_model_runs_in_worker_thread(self, fake_sentence_transformer):
        """Test that _get_model() executes inside the worker thread, not the main event loop.

        This test ensures the fix for the thread-offload regression.
        The old buggy implementation called _get_model() on the main event loop
        before offloading to thread pool.
        """
        from app.ai.embeddings.embedding_service import _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        # Record the main thread ID
        main_thread_id = threading.get_ident()
        model_init_thread_id = None

        # Use a closure to capture the thread ID when the fake constructor is called
        init_thread_id = None

        def spy_init(*args, **kwargs):
            nonlocal init_thread_id
            init_thread_id = threading.get_ident()
            mock_model = MagicMock()
            mock_model.encode.return_value = MOCK_VECTOR_384
            return mock_model

        fake_sentence_transformer.side_effect = spy_init

        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        await provider.embed_text("hello")

        # Verify the model was initialized in a different thread (worker thread)
        assert init_thread_id is not None, "SentenceTransformer should have been initialized"
        assert init_thread_id != threading.get_ident(), "Model should be initialized in worker thread, not main thread"

    async def test_concurrent_initialization_single_model(self, fake_sentence_transformer):
        """Test that concurrent calls to _get_model() initialize the model only once.

        Multiple concurrent calls to _get_model() should result in exactly one
        SentenceTransformer instantiation, with all callers receiving the same instance.
        """
        from app.ai.embeddings.embedding_service import _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        init_count = 0

        def counting_init(*args, **kwargs):
            nonlocal init_count
            init_count += 1
            mock_model = MagicMock()
            mock_model.encode.return_value = [0.1] * 384
            return mock_model

        fake_sentence_transformer.side_effect = counting_init

        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        # Call concurrently using run_in_executor to simulate concurrent access
        loop = asyncio.get_event_loop()
        results = await asyncio.gather(*[loop.run_in_executor(None, provider._get_model) for _ in range(5)])

        # Should have initialized only once despite concurrent calls
        assert init_count == 1, f"Expected 1 initialization, got {init_count}"
        # All callers should receive the same model instance
        assert len(set(id(r) for r in results)) == 1

    async def test_initialization_failure_safe(self, fake_sentence_transformer):
        """Test that initialization failure leaves provider in a retryable state.

        If SentenceTransformer construction fails, the provider should:
        - Raise the exception
        - Leave model as None (so subsequent calls can retry)
        - Release the lock so subsequent attempts can try again
        """
        from app.ai.embeddings.embedding_service import _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        def failing_init(*args, **kwargs):
            raise RuntimeError("Model download failed")

        fake_sentence_transformer.side_effect = failing_init

        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        # First attempt should raise the exception
        with pytest.raises(InvalidDocumentError, match="Failed to load SentenceTransformer model"):
            await provider.embed_text("hello")

        # Second attempt should retry and succeed
        mock_model = MagicMock()
        mock_model.encode.return_value = [0.1] * 384
        fake_sentence_transformer.side_effect = lambda *args, **kwargs: mock_model

        vector = await provider.embed_text("hello")
        assert vector == [0.1] * 384

    async def test_embed_documents_thread_safety(self, fake_sentence_transformer):
        """Verify embed_documents also uses thread-safe _get_model."""
        from app.ai.embeddings.embedding_service import _reset_sentence_transformer_model_for_testing
        _reset_sentence_transformer_model_for_testing()

        mock_model = fake_sentence_transformer.return_value
        import numpy as np
        mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])
        provider = SentenceTransformerEmbeddingProvider(model_name="test-model")

        vectors = await provider.embed_documents(["a", "b"])

        mock_model.encode.assert_called_once_with(["a", "b"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 384