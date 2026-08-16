from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.core.config import settings
from app.core.exceptions import InvalidDocumentError

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

GEMINI_REQUEST_FAILED_MESSAGE = (
    "Không thể xử lý yêu cầu AI. Vui lòng thử lại sau."
)

try:
    from google import genai
    from google.genai import types
except ImportError as exc:  # pragma: no cover - environment dependent
    genai = None
    types = None
    logger.warning("google-genai SDK is not installed: %s", exc)


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

        try:
            if isinstance(response_schema, type) and issubclass(
                response_schema, BaseModel
            ):
                return response_schema.model_validate_json(raw_text)
            parsed_json = json.loads(raw_text)
            return response_schema(**parsed_json)
        except Exception as exc:
            raise InvalidDocumentError(
                f"Failed to validate Gemini JSON response against schema {response_schema.__name__}: {exc}"
            ) from exc
