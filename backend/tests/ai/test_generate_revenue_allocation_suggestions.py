"""The revenue-allocation chain: filtering Claude's picks, then the whole run.

Scenario: Kelechi's company has Operations and Sales marked critical.
Claude — faked here — answers with department handles and percentages;
only real, unique picks may reach the queue, once.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.ai.test_llm_generate_structured import _fake_anthropic, _usage
from tests.conftest import register_verified_and_login, set_org_context
from app.core.config import settings
from app.modules.ai.enums import AIUsagePurpose
from app.modules.ai.generation import (
    RevenueAllocationContext,
    generate_revenue_allocation_suggestions,
    select_revenue_allocation_picks,
)
from app.modules.ai.llm import LLMOutputError
from app.modules.ai.models import AISuggestion, AIUsageLog
from app.modules.ai.prompts import BusinessContext
from app.modules.ai.schemas import RevenueAllocationAnswer, RevenueAllocationPick

DEPARTMENTS = "/api/v1/departments"


def _pick(handle, percentage="40"):
    return RevenueAllocationPick(
        handle=handle, revenue_allocation_percentage=Decimal(percentage), rationale="Owns delivery revenue."
    )


def _context(handle_count):
    department_ids = [uuid.uuid4() for _ in range(handle_count)]
    return RevenueAllocationContext(
        business=BusinessContext(),
        departments=[],
        handles={f"D{n}": did for n, did in enumerate(department_ids, start=1)},
    )


def _handles_kept(picks, context):
    kept = {did for did, _ in select_revenue_allocation_picks(picks, context)}
    return [label for label, did in context.handles.items() if did in kept]


# ------------------------------------------------ select_revenue_allocation_picks (pure)

def test_an_invented_handle_is_dropped_and_the_real_ones_kept():
    """D9 was never handed out: dropped, D1 and D2 kept."""
    context = _context(2)

    assert _handles_kept([_pick("D1"), _pick("D2"), _pick("D9")], context) == ["D1", "D2"]


def test_a_department_listed_twice_keeps_its_first_percentage():
    """The second, conflicting pick for the same department is dropped."""
    context = _context(1)

    kept = select_revenue_allocation_picks([_pick("D1", "40"), _pick("D1", "90")], context)

    assert len(kept) == 1
    assert kept[0][1].revenue_allocation_percentage == Decimal("40")


def test_messy_casing_and_spacing_still_resolve():
    """' d1 ' means D1 — leniency on formatting, not on facts."""
    context = _context(1)

    assert _handles_kept([_pick(" d1 ")], context) == ["D1"]


def test_mostly_invented_picks_fail_the_run():
    """Both picks point at departments that don't exist: the run is unusable, not trimmed."""
    context = _context(1)

    with pytest.raises(LLMOutputError):
        select_revenue_allocation_picks([_pick("D8"), _pick("D9")], context)


def test_no_picks_means_nothing_selected():
    """Claude proposing no allocation is a valid answer."""
    assert select_revenue_allocation_picks([], _context(1)) == []


# --------------------------------------------------------- the whole run (DB + fake Claude)

async def _org_with_two_critical_departments(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    ops = await client.post(DEPARTMENTS, json={"name": "Operations", "is_critical": True}, headers=h)
    sales = await client.post(DEPARTMENTS, json={"name": "Sales", "is_critical": True}, headers=h)
    await set_org_context(db_session, org_id)
    return org_id, {uuid.UUID(ops.json()["id"]), uuid.UUID(sales.json()["id"])}


async def _count(db_session, model):
    return await db_session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_a_run_saves_the_real_pick_on_the_strong_model(client, db_session, monkeypatch):
    """D1 is real, D9 is invented: one pending suggestion, priced on the strong tier."""
    # Which of the two departments actually sorts first as "D1" isn't
    # asserted here — the shared test session gives both the same
    # created_at, so the tie-break (id) is effectively random. Proven
    # against a real request in production, where each has its own
    # transaction and a real, distinct created_at (same caveat as
    # test_position_candidates.py's candidate-query test).
    org_id, department_ids = await _org_with_two_critical_departments(client, db_session, "rev_run1@example.com")
    seen = _fake_anthropic(
        monkeypatch, usage=_usage(), parsed_output=RevenueAllocationAnswer(picks=[_pick("D1", "60"), _pick("D9")])
    )

    created = await generate_revenue_allocation_suggestions(db_session, org_id)

    assert len(created) == 1
    suggestion = created[0]
    assert suggestion.department_id in department_ids
    assert (suggestion.suggestion_type, suggestion.status) == ("revenue_allocation", "pending")
    assert suggestion.suggested_revenue_allocation_percentage == Decimal("60")
    shown = seen["messages"][0]["content"]
    assert "D1:" in shown and "D2:" in shown
    usage_row = (await db_session.scalars(select(AIUsageLog))).one()
    assert usage_row.model == settings.anthropic_model_strong
    assert usage_row.purpose == AIUsagePurpose.AI_SUGGESTION_GENERATION.value


@pytest.mark.asyncio
async def test_running_again_creates_nothing_new(client, db_session, monkeypatch):
    """The same answer twice: the second run is a quiet no-op (still paid for, though)."""
    org_id, _ = await _org_with_two_critical_departments(client, db_session, "rev_run2@example.com")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=RevenueAllocationAnswer(picks=[_pick("D1")]))

    first = await generate_revenue_allocation_suggestions(db_session, org_id)
    second = await generate_revenue_allocation_suggestions(db_session, org_id)

    assert len(first) == 1
    assert second == []
    assert await _count(db_session, AISuggestion) == 1
    assert await _count(db_session, AIUsageLog) == 2


@pytest.mark.asyncio
async def test_nothing_critical_means_claude_is_never_called(client, db_session, monkeypatch):
    """No critical department: no candidates, no API call, no usage row."""
    owner = await register_verified_and_login(client, email="rev_run3@example.com")
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    seen = _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=RevenueAllocationAnswer(picks=[]))

    created = await generate_revenue_allocation_suggestions(db_session, org_id)

    assert created == []
    assert seen == {}
    assert await _count(db_session, AIUsageLog) == 0
