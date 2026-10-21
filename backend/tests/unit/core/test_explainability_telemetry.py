from __future__ import annotations

import logging
import uuid

import pytest
from pydantic import ValidationError

from app.core.ai_pricing import BillingTier
from app.core.config import settings
from app.core.telemetry.explainability_telemetry import (
    ExplainabilityTelemetryEvent,
    PricingStatus,
    TelemetryErrorCode,
    TelemetryOutcome,
    build_explainability_event,
    emit_explainability_event,
    minimize_identifier,
    safe_model_id,
)


def test_event_rejects_arbitrary_raw_content_fields() -> None:
    with pytest.raises(ValidationError):
        ExplainabilityTelemetryEvent(
            environment="testing",
            outcome=TelemetryOutcome.SUCCESS,
            fallback_used=False,
            application_ref=minimize_identifier(uuid.uuid4()),
            prompt="raw candidate CV",
        )


def test_prompt_like_model_id_is_not_telemetried() -> None:
    assert safe_model_id("gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"
    assert safe_model_id("Ignore previous instructions") is None
    assert safe_model_id("model\x00bad") is None


def test_reference_is_keyed_and_does_not_expose_uuid() -> None:
    application_id = uuid.uuid4()
    reference = minimize_identifier(application_id)

    assert len(reference) == 16
    assert str(application_id) not in reference
    assert reference == minimize_identifier(application_id)
    assert reference != minimize_identifier(uuid.uuid4())


def test_known_paid_usage_is_estimated_with_list_price(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GEMINI_PRICING_TIER", "paid_standard")

    event = build_explainability_event(
        application_id=uuid.uuid4(),
        outcome=TelemetryOutcome.SUCCESS,
        fallback_used=False,
        model_id="gemini-3.5-flash-lite",
        token_usage={
            "prompt_tokens": 1_000_000,
            "completion_tokens": 1_000_000,
        },
        latency_ms=12,
        ai_attempted=True,
    )

    assert event.pricing_status is PricingStatus.ESTIMATED
    assert event.pricing_tier is BillingTier.PAID_STANDARD
    assert event.estimated_cost_usd == pytest.approx(2.80)
    assert event.total_tokens == 2_000_000
    assert event.error_code is TelemetryErrorCode.NONE


def test_unknown_model_emits_unpriced_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GEMINI_PRICING_TIER", "paid_standard")

    event = build_explainability_event(
        application_id=uuid.uuid4(),
        outcome=TelemetryOutcome.SUCCESS,
        fallback_used=False,
        model_id="gemini-future-unknown",
        token_usage={"prompt_tokens": 10, "completion_tokens": 5},
        ai_attempted=True,
    )

    assert event.pricing_status is PricingStatus.UNPRICED_MODEL
    assert event.estimated_cost_usd is None
    assert event.error_code is TelemetryErrorCode.UNPRICED_MODEL


def test_missing_token_usage_is_not_priced_as_zero(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GEMINI_PRICING_TIER", "paid_standard")

    event = build_explainability_event(
        application_id=uuid.uuid4(),
        outcome=TelemetryOutcome.FALLBACK,
        fallback_used=True,
        error_code=TelemetryErrorCode.PROVIDER_TIMEOUT,
        model_id="gemini-3.5-flash-lite",
        ai_attempted=True,
    )

    assert event.pricing_status is PricingStatus.INCOMPLETE_USAGE
    assert event.estimated_cost_usd is None
    assert event.error_code is TelemetryErrorCode.PROVIDER_TIMEOUT


def test_telemetry_sink_failure_is_contained(caplog) -> None:
    event = build_explainability_event(
        application_id=uuid.uuid4(),
        outcome=TelemetryOutcome.SUCCESS,
        fallback_used=False,
    )

    def failing_sink(_event) -> None:
        raise RuntimeError("sink down")

    with caplog.at_level(
        logging.WARNING, logger="app.telemetry.explainability"
    ):
        assert emit_explainability_event(event, sink=failing_sink) is False

    assert "sink down" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_logged_payload_is_structured_and_contains_no_raw_text(caplog) -> None:
    event = build_explainability_event(
        application_id=uuid.uuid4(),
        outcome=TelemetryOutcome.SUCCESS,
        fallback_used=False,
        model_id="gemini-3.5-flash-lite",
        token_usage={"prompt_tokens": 10, "completion_tokens": 5},
        ai_attempted=True,
    )

    with caplog.at_level(
        logging.INFO, logger="app.telemetry.explainability"
    ):
        assert emit_explainability_event(event) is True

    assert "explainability_telemetry payload=" in caplog.text
    assert "raw candidate CV" not in caplog.text
