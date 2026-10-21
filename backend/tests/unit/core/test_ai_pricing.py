from __future__ import annotations

import pytest

from app.core.ai_pricing import (
    BillingTier,
    GEMINI_35_FLASH_LITE,
    calculate_estimated_cost_usd,
    resolve_pricing,
)


def test_paid_standard_list_price_formula() -> None:
    cost = calculate_estimated_cost_usd(
        GEMINI_35_FLASH_LITE,
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    assert cost == pytest.approx(2.80)


def test_paid_standard_small_request() -> None:
    cost = calculate_estimated_cost_usd(
        "models/gemini-3.5-flash-lite",
        prompt_tokens=1_000,
        completion_tokens=500,
    )

    assert cost == pytest.approx(0.0003 + 0.00125)


def test_paid_context_cache_uses_cached_input_rate() -> None:
    cost = calculate_estimated_cost_usd(
        GEMINI_35_FLASH_LITE,
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        billing_tier=BillingTier.PAID_CONTEXT_CACHE,
        cached_input_tokens=400_000,
    )

    assert cost == pytest.approx(0.18 + 0.012 + 2.50)


def test_free_tier_is_zero_cost() -> None:
    assert (
        calculate_estimated_cost_usd(
            GEMINI_35_FLASH_LITE,
            prompt_tokens=None,
            completion_tokens=None,
            billing_tier=BillingTier.FREE_TIER,
        )
        == 0.0
    )


def test_unknown_model_never_uses_a_default_rate() -> None:
    assert resolve_pricing("gemini-unlisted-model") is None
    assert (
        calculate_estimated_cost_usd(
            "gemini-unlisted-model",
            prompt_tokens=1_000,
            completion_tokens=1_000,
        )
        is None
    )


@pytest.mark.parametrize(
    ("prompt_tokens", "completion_tokens"),
    [(None, 10), (10, None), (-1, 10), (10, -1), (True, 10), (10, True)],
)
def test_incomplete_or_invalid_paid_usage_is_never_priced(
    prompt_tokens: object, completion_tokens: object
) -> None:
    assert (
        calculate_estimated_cost_usd(
            GEMINI_35_FLASH_LITE,
            prompt_tokens=prompt_tokens,  # type: ignore[arg-type]
            completion_tokens=completion_tokens,  # type: ignore[arg-type]
        )
        is None
    )


def test_context_cache_requires_cached_token_metadata() -> None:
    assert (
        calculate_estimated_cost_usd(
            GEMINI_35_FLASH_LITE,
            prompt_tokens=100,
            completion_tokens=10,
            billing_tier=BillingTier.PAID_CONTEXT_CACHE,
        )
        is None
    )


def test_cached_tokens_cannot_exceed_prompt_tokens() -> None:
    assert (
        calculate_estimated_cost_usd(
            GEMINI_35_FLASH_LITE,
            prompt_tokens=100,
            completion_tokens=10,
            billing_tier=BillingTier.PAID_CONTEXT_CACHE,
            cached_input_tokens=101,
        )
        is None
    )


def test_unknown_billing_tier_is_unpriced() -> None:
    assert resolve_pricing(GEMINI_35_FLASH_LITE, "enterprise_magic") is None
