import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.ai.providers.gemini_provider import (
    GEMINI_REQUEST_FAILED_MESSAGE,
    GeminiLLMProvider,
    _GEMINI_HTTP_RETRY_OPTIONS,
)
from app.core.config import settings
from app.core.exceptions import (
    AIProviderQuotaExceededError,
    AIProviderUnavailableError,
    InvalidDocumentError,
)
from google.genai.errors import APIError


class _DummySchema(BaseModel):
    full_name: str


def _run(coro):
    return asyncio.run(coro)


def _make_client(*, response=None, error=None):
    models = SimpleNamespace(
        generate_content=AsyncMock(return_value=response)
    )
    if error is not None:
        models.generate_content.side_effect = error
    aio = SimpleNamespace(
        models=models,
        aclose=AsyncMock(),
    )
    return SimpleNamespace(
        aio=aio,
        close=lambda: None,
        models=SimpleNamespace(
            generate_content=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("synchronous Gemini path must not be used")
            )
        ),
    )


def _success_response(text: str = '{"full_name": "Jane Doe"}'):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=7,
        ),
    )


class TestConfiguredModel:
    def test_default_model_reads_from_settings(self, monkeypatch):
        monkeypatch.setattr(
            settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash"
        )
        provider = GeminiLLMProvider(api_key="test-key")
        assert provider.model_name == "gemini-3.5-flash"

    def test_explicit_model_overrides_settings(self, monkeypatch):
        monkeypatch.setattr(
            settings, "GEMINI_GENERATION_MODEL", "model-from-settings"
        )
        provider = GeminiLLMProvider(
            api_key="test-key", model_name="gemini-3.5-flash"
        )
        assert provider.model_name == "gemini-3.5-flash"

    def test_no_deprecated_hardcoded_model(self, monkeypatch):
        monkeypatch.setattr(
            settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash"
        )
        provider = GeminiLLMProvider(api_key="test-key")
        assert "gemini-1.5-flash" not in provider.model_name


class TestNativeAsyncLifecycle:
    def test_generate_content_uses_native_async_sdk(self, monkeypatch):
        monkeypatch.setattr(
            settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash"
        )
        provider = GeminiLLMProvider(api_key="test-key")
        client = _make_client(response=_success_response())

        with patch("google.genai.Client", return_value=client):
            result = _run(
                provider.generate_structured_output(
                    prompt="Parse this resume",
                    response_schema=_DummySchema,
                )
            )

        assert result.full_name == "Jane Doe"
        assert result._token_usage == {
            "prompt_tokens": 12,
            "completion_tokens": 7,
        }
        client.aio.models.generate_content.assert_awaited_once()
        kwargs = client.aio.models.generate_content.await_args.kwargs
        assert kwargs["model"] == "gemini-3.5-flash"
        assert kwargs["contents"] == "Parse this resume"
        client.aio.aclose.assert_awaited_once()

    def test_cached_input_tokens_are_propagated_when_present(self, monkeypatch):
        monkeypatch.setattr(
            settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash"
        )
        provider = GeminiLLMProvider(api_key="test-key")
        response = _success_response()
        response.usage_metadata.cached_content_token_count = 4
        client = _make_client(response=response)

        with patch("google.genai.Client", return_value=client):
            result = _run(
                provider.generate_structured_output(
                    prompt="Parse this resume",
                    response_schema=_DummySchema,
                )
            )

        assert result._token_usage == {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "cached_input_tokens": 4,
        }

    def test_http_options_use_20_second_timeout_and_bounded_retries(self):
        provider = GeminiLLMProvider(api_key="test-key")
        client = _make_client(response=_success_response())
        captured = {}

        def _factory(**kwargs):
            captured.update(kwargs)
            return client

        with patch("google.genai.Client", side_effect=_factory):
            _run(
                provider.generate_structured_output(
                    prompt="Parse this resume",
                    response_schema=_DummySchema,
                )
            )

        options = captured["http_options"]
        assert options.timeout == 20_000
        retry = options.retry_options
        assert retry.attempts == _GEMINI_HTTP_RETRY_OPTIONS["attempts"]
        assert retry.http_status_codes == _GEMINI_HTTP_RETRY_OPTIONS[
            "http_status_codes"
        ]

    def test_aclose_runs_after_api_error(self):
        provider = GeminiLLMProvider(api_key="test-key")
        error = APIError(400, {"error": {"message": "bad request"}})
        client = _make_client(error=error)

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(InvalidDocumentError):
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        client.aio.aclose.assert_awaited_once()

    def test_cancellation_propagates_and_aclose_runs(self):
        provider = GeminiLLMProvider(api_key="test-key")
        client = _make_client(error=asyncio.CancelledError())

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(asyncio.CancelledError):
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        client.aio.aclose.assert_awaited_once()

    def test_aclose_runs_after_validation_error(self):
        provider = GeminiLLMProvider(api_key="test-key")
        client = _make_client(response=_success_response('{"wrong": 1}'))

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(InvalidDocumentError):
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        client.aio.aclose.assert_awaited_once()


class TestErrorMapping:
    def test_quota_error_maps_to_quota_exceeded_with_aclose(self):
        provider = GeminiLLMProvider(api_key="test-key")
        error = APIError(429, {"error": {"message": "quota exceeded"}})
        client = _make_client(error=error)

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(AIProviderQuotaExceededError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert exc_info.value.retry_after == 60
        client.aio.aclose.assert_awaited_once()

    def test_unavailable_error_maps_to_unavailable(self):
        provider = GeminiLLMProvider(api_key="test-key")
        error = APIError(503, {"error": {"message": "unavailable"}})
        client = _make_client(error=error)

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(AIProviderUnavailableError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert exc_info.value.retry_after == 60
        client.aio.aclose.assert_awaited_once()

    def test_non_retryable_error_is_not_quota(self):
        provider = GeminiLLMProvider(api_key="test-key")
        error = APIError(400, {"error": {"message": "bad request"}})
        client = _make_client(error=error)

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(InvalidDocumentError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        client.aio.aclose.assert_awaited_once()

    def test_missing_api_key_raises_friendly_error(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        provider = GeminiLLMProvider(api_key="")

        with pytest.raises(InvalidDocumentError) as exc_info:
            _run(
                provider.generate_structured_output(
                    prompt="Parse this resume",
                    response_schema=_DummySchema,
                )
            )

        assert "GEMINI_API_KEY" in str(exc_info.value)

    def test_empty_response_raises_and_aclose_runs(self):
        provider = GeminiLLMProvider(api_key="test-key")
        client = _make_client(
            response=SimpleNamespace(text=None, usage_metadata=None)
        )

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(InvalidDocumentError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert "empty response" in str(exc_info.value).lower()
        client.aio.aclose.assert_awaited_once()

    def test_generic_exception_is_wrapped(self):
        provider = GeminiLLMProvider(api_key="test-key")
        client = _make_client(error=TimeoutError("timed out"))

        with patch("google.genai.Client", return_value=client):
            with pytest.raises(InvalidDocumentError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        client.aio.aclose.assert_awaited_once()
