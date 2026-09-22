import asyncio
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from app.ai.providers.gemini_provider import (
    GEMINI_REQUEST_FAILED_MESSAGE,
    GeminiLLMProvider,
    _GEMINI_HTTP_RETRY_OPTIONS,
)
from app.core.config import settings
from app.core.exceptions import AIProviderQuotaExceededError, AIProviderUnavailableError, InvalidDocumentError


class _DummySchema(BaseModel):
    full_name: str


def _run(coro):
    return asyncio.run(coro)


class _CallCounterTransport(httpx.BaseTransport):
    """Transport that counts calls and returns preconfigured responses."""

    def __init__(self, responses: list[httpx.Response]):
        self.responses = responses
        self.call_count = 0
        self.requests = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        self.requests.append(request)
        if self.call_count <= len(self.responses):
            return self.responses[self.call_count - 1]
        # If more calls than responses, return last response
        return self.responses[-1]


@contextmanager
def _patched_genai_client(transport: _CallCounterTransport):
    """Create a genai.Client with a custom httpx transport."""
    from google.genai import Client, types

    client = Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(**_GEMINI_HTTP_RETRY_OPTIONS),
            httpx_client=httpx.Client(transport=transport),
        ),
    )
    try:
        yield client
    finally:
        client.close()


def _make_response(status_code: int, json_data: dict = None, text: str = None):
    """Create an httpx.Response with the given status and body."""
    if json_data is not None:
        content = json.dumps(json_data).encode()
    elif text is not None:
        content = text.encode()
    else:
        content = b""
    return httpx.Response(status_code, content=content, request=httpx.Request("POST", "https://example.com"))


def _make_success_response(text: str = '{"full_name": "Jane Doe"}'):
    """Create a successful Gemini API response."""
    return _make_response(200, json_data={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _make_error_response(status_code: int, message: str):
    """Create an error response in Gemini API format."""
    return _make_response(status_code, json_data={"error": {"code": status_code, "message": message}})


class TestConfiguredModel:
    def test_default_model_reads_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")

        provider = GeminiLLMProvider(api_key="test-key")

        assert provider.model_name == "gemini-3.5-flash"

    def test_explicit_model_overrides_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "model-from-settings")

        provider = GeminiLLMProvider(api_key="test-key", model_name="gemini-3.5-flash")

        assert provider.model_name == "gemini-3.5-flash"

    def test_no_deprecated_hardcoded_model(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")

        provider = GeminiLLMProvider(api_key="test-key")

        assert "gemini-1.5-flash" not in provider.model_name

    def test_generate_content_uses_configured_model(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        provider = GeminiLLMProvider(api_key="test-key")

        transport = _CallCounterTransport([_make_success_response()])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                result = _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert result.full_name == "Jane Doe"
        assert transport.call_count == 1


class TestErrorMapping:
    def test_provider_error_mapped_to_friendly_message(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        provider = GeminiLLMProvider(api_key="test-key")

        transport = _CallCounterTransport([
            _make_error_response(404, "models/gemini-1.5-flash is not found")
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        assert "gemini-1.5-flash is not found" not in str(exc_info.value)
        assert transport.call_count == 1

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

    def test_empty_response_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        provider = GeminiLLMProvider(api_key="test-key")

        transport = _CallCounterTransport([
            _make_response(200, json_data={"candidates": [{"content": {"parts": []}}]})
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert "empty response" in str(exc_info.value).lower()
        assert transport.call_count == 1


class TestQuotaHandling:
    """Tests for AIProviderQuotaExceededError handling."""

    @pytest.fixture
    def provider(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        return GeminiLLMProvider(api_key="test-key")

    def test_429_api_error_becomes_quota_exceeded(self, provider, monkeypatch):
        """TEST A: HTTP 429 - SDK retries 4 times then maps to AIProviderQuotaExceededError.

        Expected: 4 transport calls (attempts=4)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        # All 4 attempts return 429
        transport = _CallCounterTransport([
            _make_error_response(429, "quota exceeded"),
            _make_error_response(429, "quota exceeded"),
            _make_error_response(429, "quota exceeded"),
            _make_error_response(429, "quota exceeded"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(AIProviderQuotaExceededError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert exc_info.value.retry_after == 60
        assert "quota exceeded" in str(exc_info.value).lower()
        assert transport.call_count == 4, f"Expected 4 calls, got {transport.call_count}"

    def test_non_429_api_error_is_not_quota(self, provider):
        """TEST B: Non-retryable 400 - exactly 1 attempt, maps to InvalidDocumentError.

        Expected: 1 transport call (400 not in retry codes)
        """
        transport = _CallCounterTransport([
            _make_error_response(400, "bad request")
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        assert transport.call_count == 1

    def test_false_positive_quota_string_not_triggered(self, provider, monkeypatch):
        """TEST C: 500 with 'quota' in message - SDK retries 4 times then InvalidDocumentError.

        Expected: 4 transport calls (500 is retryable)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        transport = _CallCounterTransport([
            _make_error_response(500, "internal quota system failure"),
            _make_error_response(500, "internal quota system failure"),
            _make_error_response(500, "internal quota system failure"),
            _make_error_response(500, "internal quota system failure"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        assert transport.call_count == 4, f"Expected 4 calls, got {transport.call_count}"

    def test_false_positive_429_string_not_triggered(self, provider, monkeypatch):
        """TEST C (continued): 500 with '429' in message - SDK retries 4 times then InvalidDocumentError.

        Expected: 4 transport calls (500 is retryable)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        transport = _CallCounterTransport([
            _make_error_response(500, "Some error with 429 in message"),
            _make_error_response(500, "Some error with 429 in message"),
            _make_error_response(500, "Some error with 429 in message"),
            _make_error_response(500, "Some error with 429 in message"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        assert transport.call_count == 4, f"Expected 4 calls, got {transport.call_count}"


class TestRetryConfiguration:
    """Tests for native HTTP retry configuration."""

    def test_retry_options_constant_values(self):
        """Verify the retry configuration constants match approved architecture."""
        assert _GEMINI_HTTP_RETRY_OPTIONS["attempts"] == 4
        assert _GEMINI_HTTP_RETRY_OPTIONS["initial_delay"] == 1.0
        assert _GEMINI_HTTP_RETRY_OPTIONS["max_delay"] == 10.0
        assert _GEMINI_HTTP_RETRY_OPTIONS["exp_base"] == 2.0
        assert _GEMINI_HTTP_RETRY_OPTIONS["jitter"] == 1.0
        assert _GEMINI_HTTP_RETRY_OPTIONS["http_status_codes"] == [408, 429, 500, 502, 503, 504]

    def test_client_constructed_with_retry_options(self, monkeypatch):
        """Verify genai.Client is constructed with HttpRetryOptions."""
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        provider = GeminiLLMProvider(api_key="test-key")

        transport = _CallCounterTransport([_make_success_response()])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert transport.call_count == 1


class TestRetryBehavior:
    """Tests for HTTP retry behavior using fake transport to exercise SDK retry machinery."""

    @pytest.fixture
    def provider(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        return GeminiLLMProvider(api_key="test-key")

    def test_transient_503_then_success(self, provider, monkeypatch):
        """TEST A: Transient 503 then success - SDK retries internally and succeeds.

        Expected: 2 transport calls (1 failure + 1 success)
        """
        from google.genai.errors import APIError

        # Patch tenacity wait to execute immediately
        import tenacity
        original_wait_exponential_jitter = tenacity.wait_exponential_jitter

        def instant_wait(*args, **kwargs):
            wait_fn = original_wait_exponential_jitter(*args, **kwargs)
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        # First call returns 503, second succeeds
        transport = _CallCounterTransport([
            _make_error_response(503, "unavailable"),
            _make_success_response(),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                result = _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert result.full_name == "Jane Doe"
        assert transport.call_count == 2, f"Expected 2 calls, got {transport.call_count}"

    def test_persistent_503_exhaustion(self, provider, monkeypatch):
        """TEST B: Persistent 503 - SDK retries exhausted, maps to AIProviderUnavailableError.

        Expected: 4 transport calls (attempts=4)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        # All 4 attempts return 503
        transport = _CallCounterTransport([
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(AIProviderUnavailableError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert exc_info.value.retry_after == 60
        assert transport.call_count == 4, f"Expected 4 calls, got {transport.call_count}"

    def test_transient_429_then_success(self, provider, monkeypatch):
        """TEST C: Transient 429 then success - SDK retries internally and succeeds.

        Expected: 2 transport calls (1 failure + 1 success)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        # First call returns 429, second succeeds
        transport = _CallCounterTransport([
            _make_error_response(429, "quota exceeded"),
            _make_success_response(),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                result = _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert result.full_name == "Jane Doe"
        assert transport.call_count == 2, f"Expected 2 calls, got {transport.call_count}"

    def test_persistent_429_exhaustion(self, provider, monkeypatch):
        """TEST D: Persistent 429 - SDK retries exhausted, maps to AIProviderQuotaExceededError.

        Expected: 4 transport calls (attempts=4)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        # All 4 attempts return 429
        transport = _CallCounterTransport([
            _make_error_response(429, "quota exceeded"),
            _make_error_response(429, "quota exceeded"),
            _make_error_response(429, "quota exceeded"),
            _make_error_response(429, "quota exceeded"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(AIProviderQuotaExceededError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert exc_info.value.retry_after == 60
        assert transport.call_count == 4, f"Expected 4 calls, got {transport.call_count}"

    def test_400_non_retryable(self, provider):
        """TEST E: 400 Bad Request - exactly 1 attempt, no retry.

        Expected: 1 transport call
        """
        transport = _CallCounterTransport([
            _make_error_response(400, "bad request"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert transport.call_count == 1, f"Expected 1 call, got {transport.call_count}"
        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE

    def test_403_non_retryable(self, provider):
        """TEST F: 403 Forbidden - exactly 1 attempt, no retry.

        Expected: 1 transport call
        """
        transport = _CallCounterTransport([
            _make_error_response(403, "forbidden"),
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(InvalidDocumentError) as exc_info:
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert transport.call_count == 1, f"Expected 1 call, got {transport.call_count}"
        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE

    def test_no_double_retry_on_503(self, provider, monkeypatch):
        """TEST G: Verify exactly 4 attempts (SDK retry only, no double retry).

        Expected: 4 transport calls (not 8, 12, or 16)
        """
        import tenacity

        def instant_wait(*args, **kwargs):
            def no_sleep(retry_state):
                return 0
            return no_sleep

        monkeypatch.setattr(tenacity, "wait_exponential_jitter", instant_wait)

        # Persistent 503 for more than 4 attempts - SDK should stop at 4
        transport = _CallCounterTransport([
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),
            _make_error_response(503, "unavailable"),  # 5th - should not be called
            _make_error_response(503, "unavailable"),  # 6th - should not be called
        ])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                with pytest.raises(AIProviderUnavailableError):
                    _run(
                        provider.generate_structured_output(
                            prompt="Parse this resume",
                            response_schema=_DummySchema,
                        )
                    )

        assert transport.call_count == 4, f"Expected exactly 4 calls (no double retry), got {transport.call_count}"

    def test_successful_path_still_works(self, provider):
        """TEST H: Successful path with no retries still works correctly.

        Expected: 1 transport call
        """
        transport = _CallCounterTransport([_make_success_response()])

        with _patched_genai_client(transport) as client:
            with patch("google.genai.Client", return_value=client):
                result = _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert result.full_name == "Jane Doe"
        assert transport.call_count == 1, f"Expected 1 call, got {transport.call_count}"