"""generate_structured: the Claude call, its typed answer, and its usage row.

Scenario: a suggestion run asks Claude which positions are critical. The
Anthropic client is swapped for a fake that returns canned token counts, so
these tests need no API key, no network and cost nothing — they check what
*our* code does with a response.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from tests.conftest import register_verified_and_login, set_org_context
from app.core.config import settings
from app.modules.ai import llm
from app.modules.ai.enums import AIUsagePurpose, ModelTier
from app.modules.ai.llm import LLMOutputError, generate_structured
from app.modules.ai.models import AIUsageLog


class _Picks(BaseModel):
    """The shape we ask Claude to answer in."""

    position_ids: list[str]


def _usage(input_tokens=1_200, output_tokens=300, cache_creation=None, cache_read=None):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation=cache_creation,
        cache_read_input_tokens=cache_read,
    )


def _fake_anthropic(monkeypatch, *, usage, parsed_output, stop_reason="end_turn"):
    """Replace AsyncAnthropic with a fake; return the dict that records each request.

    ``parsed_output`` is normally one fixed answer. Pass a callable
    (``kwargs -> answer``, see ``_by_output_format`` below) instead when a
    single run makes more than one Claude call expecting different answer
    shapes — e.g. ``run_generation`` now asks for both a
    ``CriticalPositionAnswer`` and a ``RevenueAllocationAnswer``.
    """
    seen = {}

    async def parse(**kwargs):
        seen.update(kwargs)
        answer = parsed_output(kwargs) if callable(parsed_output) else parsed_output
        return SimpleNamespace(usage=usage, parsed_output=answer, stop_reason=stop_reason)

    class _Client:
        messages = SimpleNamespace(parse=parse)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(llm, "AsyncAnthropic", lambda **kwargs: _Client())
    return seen


def _by_output_format(answers_by_type: dict):
    """A ``parsed_output`` dispatcher for ``_fake_anthropic``.

    ``answers_by_type`` maps an answer class (e.g. ``CriticalPositionAnswer``)
    to the canned answer to return when that class is the one requested —
    read off the real request's ``output_format``, exactly what the live API
    would branch on.
    """

    def pick(kwargs):
        return answers_by_type[kwargs["output_format"]]

    return pick


async def _org(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    return org_id


async def _usage_rows(db_session):
    return (await db_session.scalars(select(AIUsageLog))).all()


async def _ask(db_session, org_id, tier=ModelTier.STRONG):
    return await generate_structured(
        db_session,
        organization_id=org_id,
        purpose=AIUsagePurpose.AI_SUGGESTION_GENERATION,
        tier=tier,
        system="You flag critical positions.",
        prompt="Positions: GM, Driver",
        output_type=_Picks,
    )


@pytest.mark.asyncio
async def test_the_typed_answer_comes_back_and_one_usage_row_is_saved(client, db_session, monkeypatch):
    """1,200 in / 300 out on the strong model: answer returned, $0.0054 recorded."""
    org_id = await _org(client, db_session, "llm_gen1@example.com")
    answer = _Picks(position_ids=["gm"])
    seen = _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=answer)

    result = await _ask(db_session, org_id)

    assert result == answer
    assert seen["output_format"] is _Picks
    assert seen["system"] == "You flag critical positions."
    assert seen["messages"] == [{"role": "user", "content": "Positions: GM, Driver"}]
    (row,) = await _usage_rows(db_session)
    assert (str(row.organization_id), row.purpose, row.model) == (
        str(org_id),
        "ai_suggestion_generation",
        settings.anthropic_model_strong,
    )
    assert (row.prompt_tokens, row.completion_tokens) == (1_200, 300)
    assert row.estimated_cost_usd == Decimal("0.0054")


@pytest.mark.asyncio
async def test_each_tier_calls_its_own_model_and_logs_it(client, db_session, monkeypatch):
    """FAST and STRONG hit different models, and the log says which."""
    org_id = await _org(client, db_session, "llm_gen2@example.com")
    seen = _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_Picks(position_ids=[]))

    await _ask(db_session, org_id, tier=ModelTier.FAST)
    fast_model = seen["model"]
    await _ask(db_session, org_id, tier=ModelTier.STRONG)
    strong_model = seen["model"]

    assert fast_model == settings.anthropic_model_fast
    assert strong_model == settings.anthropic_model_strong
    assert fast_model != strong_model
    assert {row.model for row in await _usage_rows(db_session)} == {fast_model, strong_model}


@pytest.mark.asyncio
async def test_cache_tokens_are_recorded_and_priced(client, db_session, monkeypatch):
    """Cache writes (5m + 1h) and reads land in their own columns and in the cost."""
    org_id = await _org(client, db_session, "llm_gen3@example.com")
    _fake_anthropic(
        monkeypatch,
        usage=_usage(
            input_tokens=1_000_000,
            output_tokens=0,
            cache_creation=SimpleNamespace(
                ephemeral_5m_input_tokens=1_000_000, ephemeral_1h_input_tokens=1_000_000
            ),
            cache_read=1_000_000,
        ),
        parsed_output=_Picks(position_ids=[]),
    )

    await _ask(db_session, org_id)

    (row,) = await _usage_rows(db_session)
    assert (row.prompt_tokens, row.cache_write_tokens, row.cache_read_tokens) == (
        1_000_000,
        2_000_000,
        1_000_000,
    )
    # Sonnet: $2 input + $2.50 (5m write) + $4 (1h write) + $0.20 (hit)
    assert row.estimated_cost_usd == Decimal("8.7000")


@pytest.mark.asyncio
async def test_an_unusable_answer_raises_but_the_spend_is_still_recorded(client, db_session, monkeypatch):
    """A refusal or cut-off reply cost tokens too, so its usage row is kept."""
    org_id = await _org(client, db_session, "llm_gen4@example.com")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=None, stop_reason="max_tokens")

    with pytest.raises(LLMOutputError, match="max_tokens"):
        await _ask(db_session, org_id)

    (row,) = await _usage_rows(db_session)
    assert (row.prompt_tokens, row.completion_tokens) == (1_200, 300)
