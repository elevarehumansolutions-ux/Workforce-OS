"""Shared LLM-calling utility: model choice, cost estimate, and the Claude call itself."""

import logging
import uuid
from decimal import Decimal
from typing import TypeVar

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from .enums import AIUsagePurpose, ModelTier
from .repository import AIUsageLogRepository

T = TypeVar("T")

logger = logging.getLogger(__name__)

ANTHROPIC_TOKEN_PRICES: dict[str, dict[str, Decimal | None]] = {
    # USD per 1,000,000 tokens, per model. A cache rate of None means "unknown",
    # not "free" (see estimate_cost_usd). No call site enables prompt caching yet,
    # so the cache buckets are 0 today.

    "claude-haiku-4-5": {
        "input_per_mtok": Decimal("1.00"),
        "output_per_mtok": Decimal("5.00"),
        "cache_write_5m_per_mtok": Decimal("1.25"),
        "cache_write_1h_per_mtok": Decimal("2.00"),
        "cache_hit_per_mtok": Decimal("0.10"),
    },

    "claude-sonnet-5": {
        "input_per_mtok": Decimal("2.00"),
        "output_per_mtok": Decimal("10.00"),
        "cache_write_5m_per_mtok": Decimal("2.50"),
        "cache_write_1h_per_mtok": Decimal("4.00"),
        "cache_hit_per_mtok": Decimal("0.20"),
    },
}

_MTOK = Decimal(1_000_000)


def model_for_tier(tier: ModelTier) -> str:
    """Return the configured model id for a tier."""
    return {
        ModelTier.FAST: settings.anthropic_model_fast,
        ModelTier.STRONG: settings.anthropic_model_strong,
    }[tier]


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_5m_tokens: int = 0,
    cache_write_1h_tokens: int = 0,
    cache_hit_tokens: int = 0,
) -> Decimal | None:
    """Cost of one Anthropic Messages API call, or None if the model isn't priced.

    Cache token counts default to 0 — none of the current call sites
    enable prompt caching, so `response.usage.cache_creation_input_tokens`/
    `cache_read_input_tokens` are never populated yet. If a nonzero cache
    count is ever passed for a model whose cache rate isn't known (None in
    ANTHROPIC_TOKEN_PRICES), this returns None rather than silently
    pricing that portion as free.
    """
    rates = ANTHROPIC_TOKEN_PRICES.get(model)
    if rates is None:
        logger.warning("No price known for model %s; cost not estimated", model)
        return None
    
    def _priced(tokens: int, rate: Decimal | None) -> Decimal | None:
        """Compute cost for a token bucket, or None if the rate is unknown."""
        if tokens <= 0:
            return Decimal("0")
        if rate is None:
            return None
        return (Decimal(tokens) / _MTOK) * rate
    
    parts = [
        _priced(input_tokens, rates["input_per_mtok"]),
        _priced(output_tokens, rates["output_per_mtok"]),
        _priced(cache_write_5m_tokens, rates.get("cache_write_5m_per_mtok")),
        _priced(cache_write_1h_tokens, rates.get("cache_write_1h_per_mtok")),
        _priced(cache_hit_tokens, rates.get("cache_hit_per_mtok")),
    ]

    if any(p is None for p in parts):
        return None
    return sum(parts, Decimal(0)).quantize(Decimal("0.0001"))


class LLMOutputError(Exception):
    """Claude answered, but not with a usable result (refused, cut off, or off-schema)."""


async def generate_structured(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    purpose: AIUsagePurpose,
    tier: ModelTier,
    system: str,
    prompt: str,
    output_type: type[T],
    max_tokens: int = 8000,
) -> T:
    """Ask Claude for an answer shaped like ``output_type``; record the call's usage.

    Raises:
        LLMOutputError: Claude replied without a usable answer. The usage
            row is still recorded - the tokens were spent.
        anthropic.APIError: transport/API failures the SDK could not retry
            away; the caller decides whether to retry the whole job.
    """
    model = model_for_tier(tier)
    async with AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
        response = await client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{
                "role": "user",
                "content": prompt,
            }],
            output_format=output_type
        )

        usage = response.usage
        written_5m = usage.cache_creation.ephemeral_5m_input_tokens if usage.cache_creation else 0
        written_1h = usage.cache_creation.ephemeral_1h_input_tokens if usage.cache_creation else 0
        cache_read = usage.cache_read_input_tokens or 0
        await AIUsageLogRepository(db).create_usage_log(
            organization_id=organization_id,
            purpose=purpose.value,
            model=model,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            cache_write_tokens=written_5m + written_1h,
            cache_read_tokens=cache_read,
            estimated_cost_usd=estimate_cost_usd(
                model, usage.input_tokens, usage.output_tokens, written_5m, written_1h, cache_read
            ),
        )

        if response.parsed_output is None:
            raise LLMOutputError(f"No usable answer from {model} (stop_reason={response.stop_reason})")

        return response.parsed_output
