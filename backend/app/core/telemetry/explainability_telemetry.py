"""Runtime-validated, allowlisted telemetry for match explanations.

This module deliberately does not accept arbitrary dictionaries for
publication. Callers construct an ``ExplainabilityTelemetryEvent`` whose schema
contains only bounded operational fields. Raw CV/JD content, prompts, narrative
text, exception messages and stack traces have no field and are rejected by
``extra="forbid"``.

Telemetry is best-effort observability: a validation, sink or logger failure
must never change the explanation response.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date
from enum import Enum
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.ai_pricing import (
    BillingTier,
    ModelPricing,
    calculate_estimated_cost_usd,
    parse_billing_tier,
    resolve_pricing,
)
from app.core.config import settings

logger = logging.getLogger("app.telemetry.explainability")

TELEMETRY_EVENT_TYPE = "match_explanation"
TELEMETRY_EVENT_VERSION = 1

_MODEL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"
_REFERENCE_PATTERN = r"^[a-f0-9]{16}$"


class TelemetryOutcome(str, Enum):
    SUCCESS = "success"
    FALLBACK = "fallback"
    ERROR = "error"


class TelemetryErrorCode(str, Enum):
    NONE = "NONE"
    INVALID_INPUT = "INVALID_INPUT"
    PROVIDER_QUOTA_EXCEEDED = "PROVIDER_QUOTA_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_NARRATIVE = "INVALID_NARRATIVE"
    SCORE_CONTRADICTION = "SCORE_CONTRADICTION"
    UNPRICED_MODEL = "UNPRICED_MODEL"
    TOKEN_USAGE_MISSING = "TOKEN_USAGE_MISSING"
    REDIS_UNAVAILABLE = "REDIS_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TELEMETRY_ERROR = "TELEMETRY_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PricingStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    FREE = "free"
    ESTIMATED = "estimated"
    UNPRICED_MODEL = "unpriced_model"
    INCOMPLETE_USAGE = "incomplete_usage"


class ExplainabilityTelemetryEvent(BaseModel):
    """One allowlisted explanation telemetry record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_version: Literal[1] = TELEMETRY_EVENT_VERSION
    event_type: Literal["match_explanation"] = TELEMETRY_EVENT_TYPE
    environment: Literal[
        "development", "staging", "production", "testing", "unknown"
    ]
    outcome: TelemetryOutcome
    fallback_used: bool
    error_code: TelemetryErrorCode = TelemetryErrorCode.NONE
    application_ref: str = Field(..., pattern=_REFERENCE_PATTERN)
    model_id: str | None = Field(default=None, pattern=_MODEL_ID_PATTERN)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    pricing_status: PricingStatus = PricingStatus.NOT_APPLICABLE
    pricing_tier: BillingTier | None = None
    pricing_effective_date: date | None = None
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0, le=3_600_000)
    cache_state: Literal["not_cached", "cached", "db_replay"] = "not_cached"
    summary_source: Literal["deterministic", "ai_generated"] = "deterministic"

    @field_validator("application_ref")
    @classmethod
    def _validate_reference(cls, value: str) -> str:
        if not value or not all(char in "0123456789abcdef" for char in value):
            raise ValueError("application_ref must be a lowercase hex digest")
        return value


def normalize_environment(value: object) -> str:
    if isinstance(value, str) and value in {
        "development",
        "staging",
        "production",
        "testing",
    }:
        return value
    return "unknown"


def safe_model_id(value: object) -> str | None:
    """Return a bounded model identifier or ``None``; never pass prose through."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 128:
        return None
    if not all(
        char.isascii() and (char.isalnum() or char in "._:/-")
        for char in candidate
    ):
        return None
    if candidate[0] in "._:/-":
        return None
    return candidate


def minimize_identifier(value: object) -> str:
    """Return a stable, keyed 16-hex reference instead of a raw identifier."""
    material = str(value).encode("utf-8")
    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, material, hashlib.sha256).hexdigest()[:16]


def _token_value(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def normalize_token_usage(value: object) -> dict[str, int | None] | None:
    """Extract only known integer token counts from provider metadata."""
    if not isinstance(value, dict):
        return None
    prompt = _token_value(value.get("prompt_tokens"))
    completion = _token_value(value.get("completion_tokens"))
    cached = _token_value(value.get("cached_input_tokens"))
    if prompt is None and completion is None and cached is None:
        return None
    total = None
    if prompt is not None and completion is not None:
        total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_input_tokens": cached,
        "total_tokens": total,
    }


def _pricing_fields(
    *,
    model_id: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_input_tokens: int | None,
    ai_attempted: bool,
) -> tuple[PricingStatus, ModelPricing | None, float | None]:
    if not ai_attempted:
        return PricingStatus.NOT_APPLICABLE, None, None

    tier = parse_billing_tier(settings.GEMINI_PRICING_TIER)
    if tier is None:
        return PricingStatus.UNPRICED_MODEL, None, None
    pricing = resolve_pricing(model_id, tier)
    if pricing is None:
        return PricingStatus.UNPRICED_MODEL, None, None

    estimate = calculate_estimated_cost_usd(
        model_id,
        prompt_tokens,
        completion_tokens,
        billing_tier=tier,
        cached_input_tokens=cached_input_tokens,
    )
    if estimate is None:
        return PricingStatus.INCOMPLETE_USAGE, pricing, None
    if pricing.billing_tier is BillingTier.FREE_TIER:
        return PricingStatus.FREE, pricing, 0.0
    return PricingStatus.ESTIMATED, pricing, estimate


def build_explainability_event(
    *,
    application_id: object,
    outcome: TelemetryOutcome,
    fallback_used: bool,
    error_code: TelemetryErrorCode = TelemetryErrorCode.NONE,
    model_id: object = None,
    token_usage: object = None,
    latency_ms: int = 0,
    cache_state: str = "not_cached",
    summary_source: str = "deterministic",
    ai_attempted: bool = False,
) -> ExplainabilityTelemetryEvent:
    """Build a validated event, computing pricing only from known metadata."""
    usage = normalize_token_usage(token_usage) or {}
    safe_model = safe_model_id(model_id)
    pricing_status, pricing, estimate = _pricing_fields(
        model_id=safe_model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        cached_input_tokens=usage.get("cached_input_tokens"),
        ai_attempted=ai_attempted,
    )

    resolved_error = error_code
    if (
        resolved_error is TelemetryErrorCode.NONE
        and pricing_status is PricingStatus.UNPRICED_MODEL
    ):
        resolved_error = TelemetryErrorCode.UNPRICED_MODEL
    elif (
        resolved_error is TelemetryErrorCode.NONE
        and pricing_status is PricingStatus.INCOMPLETE_USAGE
    ):
        resolved_error = TelemetryErrorCode.TOKEN_USAGE_MISSING

    safe_cache_state = (
        cache_state
        if cache_state in {"not_cached", "cached", "db_replay"}
        else "not_cached"
    )
    safe_summary_source = (
        summary_source
        if summary_source in {"deterministic", "ai_generated"}
        else "deterministic"
    )

    return ExplainabilityTelemetryEvent(
        environment=normalize_environment(settings.ENVIRONMENT),
        outcome=outcome,
        fallback_used=fallback_used,
        error_code=resolved_error,
        application_ref=minimize_identifier(application_id),
        model_id=safe_model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        cached_input_tokens=usage.get("cached_input_tokens"),
        total_tokens=usage.get("total_tokens"),
        pricing_status=pricing_status,
        pricing_tier=pricing.billing_tier if pricing else None,
        pricing_effective_date=pricing.effective_date if pricing else None,
        estimated_cost_usd=estimate,
        latency_ms=max(0, min(int(latency_ms), 3_600_000)),
        cache_state=safe_cache_state,
        summary_source=safe_summary_source,
    )


TelemetrySink = Callable[[ExplainabilityTelemetryEvent], None]


def emit_explainability_event(
    event: ExplainabilityTelemetryEvent,
    *,
    sink: TelemetrySink | None = None,
) -> bool:
    """Emit a validated event; return ``False`` on any telemetry failure."""
    try:
        validated = ExplainabilityTelemetryEvent.model_validate(
            event.model_dump(mode="python")
        )
        if sink is not None:
            sink(validated)
        else:
            logger.info(
                "explainability_telemetry payload=%s",
                json.dumps(
                    validated.model_dump(mode="json"),
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry must never break request
        logger.warning(
            "explainability_telemetry_failed error=%s",
            type(exc).__name__,
        )
        return False
