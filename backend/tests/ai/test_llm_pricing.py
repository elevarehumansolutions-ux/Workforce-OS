"""Model tiers and cost estimation in the shared LLM utility.

Scenario: a suggestion run finishes on the STRONG tier having used 1,200
input and 300 output tokens. The usage log must record which model served
it and what it cost — and a model nobody priced yet must never crash a call
that already succeeded.
"""
from decimal import Decimal

from app.core.config import settings
from app.modules.ai.enums import ModelTier
from app.modules.ai.llm import estimate_cost_usd, model_for_tier


def test_each_tier_maps_to_its_configured_model():
    """FAST and STRONG resolve to whatever config names for them."""
    assert model_for_tier(ModelTier.FAST) == settings.anthropic_model_fast
    assert model_for_tier(ModelTier.STRONG) == settings.anthropic_model_strong


def test_a_sonnet_call_costs_what_the_price_list_says():
    """1,200 in x $2 + 300 out x $10, per million tokens = $0.0054."""
    assert estimate_cost_usd("claude-sonnet-5", 1_200, 300) == Decimal("0.0054")


def test_the_fast_model_is_cheaper_for_the_same_tokens():
    """1,200 in x $1 + 300 out x $5, per million tokens = $0.0027."""
    assert estimate_cost_usd("claude-haiku-4-5", 1_200, 300) == Decimal("0.0027")


def test_cache_buckets_are_priced_at_their_own_rates():
    """Sonnet: 1M x $2.50 (5m write) + 1M x $4 (1h write) + 1M x $0.20 (hit)."""
    cost = estimate_cost_usd(
        "claude-sonnet-5",
        0,
        0,
        cache_write_5m_tokens=1_000_000,
        cache_write_1h_tokens=1_000_000,
        cache_hit_tokens=1_000_000,
    )
    assert cost == Decimal("6.7000")


def test_the_cost_is_rounded_to_what_the_column_stores():
    """The usage log column is NUMERIC(10,4): four decimal places, no more."""
    cost = estimate_cost_usd("claude-sonnet-5", 1_234, 567)
    assert cost == cost.quantize(Decimal("0.0001"))


def test_an_unpriced_model_gives_none_instead_of_crashing():
    """A model missing from the price table yields None, not an exception."""
    assert estimate_cost_usd("claude-some-future-model", 1_200, 300) is None
