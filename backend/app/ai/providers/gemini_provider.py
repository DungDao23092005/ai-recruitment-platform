from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.core.config import settings
from app.core.exceptions import AIProviderQuotaExceededError, AIProviderUnavailableError, InvalidDocumentError

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

GEMINI_REQUEST_FAILED_MESSAGE = (
    "Không thể xử lý yêu cầu AI. Vui lòng thử lại sau."
)

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
except ImportError as exc:  # pragma: no cover - environment dependent
    genai = None
    types = None
    APIError = None
    logger.warning("google-genai SDK is not installed: %s", exc)


@dataclass
class TokenUsage:
    """Token usage metadata from LLM provider."""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


class GeminiLLMProvider(BaseLLMProvider):
    """Google Gemini LLM provider implementation using google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_GENERATION_MODEL

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
    ) -> T:
        """Generate structured output adhering to a Pydantic schema using Gemini."""
        if not prompt or not prompt.strip():
            raise InvalidDocumentError("Prompt text for LLM generation cannot be empty")

        if not self.api_key:
            raise InvalidDocumentError("GEMINI_API_KEY is not configured")

        if genai is None:
            raise InvalidDocumentError(
                "google-genai SDK is not installed. "
                "Please install google-genai and restart the service."
            )

        client = genai.Client(api_key=self.api_key)

        config_args: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_args)

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
        except APIError as exc:
            logger.error(
                "Gemini API request failed for model %s: %s",
                self.model_name,
                exc,
            )
            if exc.code == 429:
                raise AIProviderQuotaExceededError(
                    "AI provider quota exceeded.",
                    retry_after=60,
                ) from exc
            if exc.code == 503:
                raise AIProviderUnavailableError(
                    "AI provider temporarily unavailable.",
                    retry_after=60,
                ) from exc

            raise InvalidDocumentError(GEMINI_REQUEST_FAILED_MESSAGE) from exc
        except Exception as exc:
            logger.error(
                "Gemini API request failed for model %s: %s",
                self.model_name,
                exc,
            )
            raise InvalidDocumentError(GEMINI_REQUEST_FAILED_MESSAGE) from exc

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise InvalidDocumentError("Gemini API returned an empty response")

        # Extract token usage metadata if available
        token_usage = None
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            prompt_tokens = getattr(usage_metadata, "prompt_token_count", None)
            completion_tokens = getattr(usage_metadata, "candidates_token_count", None)
            if prompt_tokens is not None or completion_tokens is not None:
                token_usage = TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

        try:
            if isinstance(response_schema, type) and issubclass(
                response_schema, BaseModel
            ):
                parsed = response_schema.model_validate_json(raw_text)
                # Attach token usage to the response object if available
                if token_usage is not None:
                    object.__setattr__(parsed, "_token_usage", token_usage.to_dict())
                return parsed
            parsed_json = json.loads(raw_text)
            parsed = response_schema(**parsed_json)
            if token_usage is not None:
                object.__setattr__(parsed, "_token_usage", token_usage.to_dict())
            return parsed
        except Exception as exc:
            raise InvalidDocumentError(
                f"Failed to validate Gemini JSON response against schema {response_schema.__name__}: {exc}"
            ) from exc
