import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.ai.providers.gemini_provider import (
    GEMINI_REQUEST_FAILED_MESSAGE,
    GeminiLLMProvider,
)
from app.core.config import settings
from app.core.exceptions import InvalidDocumentError


class _DummySchema(BaseModel):
    full_name: str


def _run(coro):
    return asyncio.run(coro)


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

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"full_name": "Jane Doe"}'
        )

        with patch("google.genai.Client", return_value=mock_client):
            result = _run(
                provider.generate_structured_output(
                    prompt="Parse this resume",
                    response_schema=_DummySchema,
                )
            )

        assert result.full_name == "Jane Doe"
        mock_client.models.generate_content.assert_called_once()
        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-3.5-flash"


class TestErrorMapping:
    def test_provider_error_mapped_to_friendly_message(self, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_GENERATION_MODEL", "gemini-3.5-flash")
        provider = GeminiLLMProvider(api_key="test-key")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError(
            "404 NOT_FOUND: models/gemini-1.5-flash is not found"
        )

        with patch("google.genai.Client", return_value=mock_client):
            with pytest.raises(InvalidDocumentError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert str(exc_info.value) == GEMINI_REQUEST_FAILED_MESSAGE
        assert "gemini-1.5-flash is not found" not in str(exc_info.value)

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

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text=None)

        with patch("google.genai.Client", return_value=mock_client):
            with pytest.raises(InvalidDocumentError) as exc_info:
                _run(
                    provider.generate_structured_output(
                        prompt="Parse this resume",
                        response_schema=_DummySchema,
                    )
                )

        assert "empty response" in str(exc_info.value)