"""Model-specific Gemini pricing catalog and inference-cost estimates.

The values in this catalog are *public list prices*, not the amount a customer
will necessarily be billed. Enterprise agreements, credits, taxes, currency
conversion and context-cache storage can all change the invoice. Every value
produced here is therefore named ``estimated_cost_usd``.

Source (retrieved 2026-10-21):
https://ai.google.dev/gemini-api/docs/pricing

Gemini 3.5 Flash-Lite Standard tier:
* Free tier: no charge for input or output.
* Paid tier: $0.30 / 1M input tokens and $2.50 / 1M output tokens.
* Context caching: $0.03 / 1M cached input tokens, plus $1.00 / 1M tokens
  per hour of cache storage. Cache storage is not included in an
  inference-time estimate because token usage metadata does not report
  storage duration.

Unknown model IDs are deliberately unpriced. There is no catch-all/default
rate: silently applying another model's price would be misleading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Mapping

PRICING_SOURCE_URL = "https://ai.google.dev/gemini-api/docs/pricing"
PRICING_SOURCE_RETRIEVED_DATE = date(2026, 10, 21)


class BillingTier(str, Enum):
    FREE_TIER = "free_tier"
    PAID_STANDARD = "paid_standard"
    PAID_CONTEXT_CACHE = "paid_context_cache"


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    billing_tier: BillingTier
    input_usd_per_1m: float
    output_usd_per_1m: float
    cached_input_usd_per_1m: float | None
    cache_storage_usd_per_1m_per_hour: float | None
    effective_date: date
    source_url: str = PRICING_SOURCE_URL
    source_retrieved_date: date = PRICING_SOURCE_RETRIEVED_DATE
    notes: str = "Public list price; excludes negotiated discounts, credits, taxes and currency conversion."


GEMINI_35_FLASH_LITE = "gemini-3.5-flash-lite"

GEMINI_PRICING_CATALOG: Mapping[
    str, Mapping[BillingTier, ModelPricing]
] = {
    GEMINI_35_FLASH_LITE: {
        BillingTier.FREE_TIER: ModelPricing(
            model_id=GEMINI_35_FLASH_LITE,
            billing_tier=BillingTier.FREE_TIER,
            input_usd_per_1m=0.0,
            output_usd_per_1m=0.0,
            cached_input_usd_per_1m=None,
            cache_storage_usd_per_1m_per_hour=None,
            effective_date=date(2026, 10, 19),
            notes=(
                "Free tier is no-charge; context caching is not available on "
                "the free tier."
            ),
        ),
        BillingTier.PAID_STANDARD: ModelPricing(
            model_id=GEMINI_35_FLASH_LITE,
            billing_tier=BillingTier.PAID_STANDARD,
            input_usd_per_1m=0.30,
            output_usd_per_1m=2.50,
            cached_input_usd_per_1m=None,
            cache_storage_usd_per_1m_per_hour=None,
            effective_date=date(2026, 10, 19),
        ),
        BillingTier.PAID_CONTEXT_CACHE: ModelPricing(
            model_id=GEMINI_35_FLASH_LITE,
            billing_tier=BillingTier.PAID_CONTEXT_CACHE,
            input_usd_per_1m=0.30,
            output_usd_per_1m=2.50,
            cached_input_usd_per_1m=0.03,
            cache_storage_usd_per_1m_per_hour=1.00,
            effective_date=date(2026, 10, 19),
            notes=(
                "Inference estimate uses the cached-input rate; cache storage "
                "($1.00 / 1M tokens per hour) is excluded because token usage "
                "metadata has no storage duration."
            ),
        ),
    }
}


def normalize_model_id(model_name: object) -> str | None:
    """Return a safe catalog key, or ``None`` for malformed/unknown input."""
    if not isinstance(model_name, str):
        return None
    normalized = model_name.strip()
    if normalized.startswith("models/"):
        normalized = normalized[len("models/") :]
    return normalized or None


def parse_billing_tier(value: object) -> BillingTier | None:
    """Parse a configured tier without falling back to a default rate."""
    if isinstance(value, BillingTier):
        return value
    if not isinstance(value, str):
        return None
    try:
        return BillingTier(value.strip().lower())
    except ValueError:
        return None


def resolve_pricing(
    model_name: object,
    billing_tier: object = BillingTier.PAID_STANDARD,
) -> ModelPricing | None:
    """Resolve an exact model + tier, or ``None`` when unpriced."""
    model_id = normalize_model_id(model_name)
    tier = parse_billing_tier(billing_tier)
    if model_id is None or tier is None:
        return None
    return GEMINI_PRICING_CATALOG.get(model_id, {}).get(tier)


def _valid_token_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def calculate_estimated_cost_usd(
    model_name: object,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    *,
    billing_tier: object = BillingTier.PAID_STANDARD,
    cached_input_tokens: int | None = None,
) -> float | None:
    """Estimate one inference request's list-price cost in USD.

    Returns ``None`` when the model/tier is not in the catalog, a paid tier's
    token metadata is incomplete, or context-cache token metadata is required
    but unavailable. A paid estimate is never produced from partial usage.

    ``prompt_tokens`` is treated as total input tokens. For the context-cache
    tier, ``cached_input_tokens`` must be known and must not exceed it.
    """
    pricing = resolve_pricing(model_name, billing_tier)
    if pricing is None:
        return None

    if pricing.billing_tier is BillingTier.FREE_TIER:
        return 0.0

    if not _valid_token_count(prompt_tokens) or not _valid_token_count(
        completion_tokens
    ):
        return None

    prompt = int(prompt_tokens)
    completion = int(completion_tokens)

    if pricing.billing_tier is BillingTier.PAID_CONTEXT_CACHE:
        if not _valid_token_count(cached_input_tokens):
            return None
        cached = int(cached_input_tokens)
        if cached > prompt:
            return None
        if pricing.cached_input_usd_per_1m is None:
            return None
        uncached = prompt - cached
        return (
            (uncached / 1_000_000) * pricing.input_usd_per_1m
            + (cached / 1_000_000) * pricing.cached_input_usd_per_1m
            + (completion / 1_000_000) * pricing.output_usd_per_1m
        )

    return (
        (prompt / 1_000_000) * pricing.input_usd_per_1m
        + (completion / 1_000_000) * pricing.output_usd_per_1m
    )
