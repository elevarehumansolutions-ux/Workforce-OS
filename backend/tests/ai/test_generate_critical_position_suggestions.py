"""The critical-position chain: filtering Claude's picks, then the whole run.

Scenario: Adaeze's org has Operations (critical) with Dispatcher and Driver.
Claude — faked here, so no key, no network, no cost — answers with labels;
only real, unique, in-cap picks may reach her queue, once.
"""
import uuid

import pytest
from sqlalchemy import func, select

from tests.ai.test_llm_generate_structured import _fake_anthropic, _usage
from tests.conftest import register_verified_and_login, set_org_context
from app.core.config import settings
from app.modules.ai.enums import AIUsagePurpose
from app.modules.ai.generation import (
    CriticalPositionContext,
    generate_critical_position_suggestions,
    select_critical_picks,
)
from app.modules.ai.llm import LLMOutputError
from app.modules.ai.models import AISuggestion, AIUsageLog
from app.modules.ai.prompts import BusinessContext
from app.modules.ai.schemas import CriticalPositionAnswer, CriticalPositionPick


def _pick(handle, risk_level="high"):
    return CriticalPositionPick(
        handle=handle,
        criticality_type="operational",
        risk_level=risk_level,
        rationale="Keeps deliveries moving.",
    )


def _context(departments):
    """A hand-built context: ``departments`` lists each position's department, P1 first."""
    position_ids = [uuid.uuid4() for _ in departments]
    department_ids = {name: uuid.uuid4() for name in set(departments)}
    return CriticalPositionContext(
        business=BusinessContext(),
        departments=[],
        handles={f"P{n}": pid for n, pid in enumerate(position_ids, start=1)},
        department_of={pid: department_ids[name] for pid, name in zip(position_ids, departments)},
    )


def _handles_kept(picks, context):
    """The canonical labels (P1, P2...) of the positions that survived, in label order."""
    kept = {pid for pid, _ in select_critical_picks(picks, context)}
    return [label for label, pid in context.handles.items() if pid in kept]


# ------------------------------------------------- select_critical_picks (pure)

def test_the_cap_and_grounding_drop_the_extras(monkeypatch):
    """Cap 3: P4 is over the limit, P9 was never handed out. P1-P3 survive."""
    monkeypatch.setattr(settings, "ai_max_critical_positions_per_department_per_run", 3)
    context = _context(["ops"] * 6)

    picks = [_pick(h) for h in ("P1", "P2", "P3", "P4", "P9")]

    assert _handles_kept(picks, context) == ["P1", "P2", "P3"]


def test_the_cap_counts_each_department_separately(monkeypatch):
    """Cap 1: one pick from Operations and one from Sales both fit."""
    monkeypatch.setattr(settings, "ai_max_critical_positions_per_department_per_run", 1)
    context = _context(["ops", "ops", "sales"])

    picks = [_pick(h) for h in ("P1", "P2", "P3")]

    assert _handles_kept(picks, context) == ["P1", "P3"]


def test_duplicates_and_messy_labels_are_tolerated(monkeypatch):
    """'P1' listed twice counts once and takes no extra cap slot; ' p2 ' means P2."""
    monkeypatch.setattr(settings, "ai_max_critical_positions_per_department_per_run", 2)
    context = _context(["ops"] * 3)

    picks = [_pick("P1"), _pick("p1"), _pick(" p2 "), _pick("P3")]

    assert _handles_kept(picks, context) == ["P1", "P2"]


def test_an_answer_that_is_mostly_invented_fails_the_run():
    """Two of three labels never existed: the run is unusable, not trimmed."""
    context = _context(["ops"] * 2)

    with pytest.raises(LLMOutputError):
        select_critical_picks([_pick("P1"), _pick("P8"), _pick("P9")], context)


def test_no_picks_means_nothing_selected():
    """Claude finding nothing critical is a valid answer."""
    assert select_critical_picks([], _context(["ops"])) == []


# ------------------------------------------------- the whole run (DB + fake Claude)

async def _org_with_operations(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(
        "/api/v1/departments", json={"name": "Operations", "is_critical": True}, headers=h
    )
    positions = {}
    for title in ("Dispatcher", "Driver"):
        resp = await client.post(
            "/api/v1/positions", json={"department_id": dept.json()["id"], "title": title}, headers=h
        )
        positions[title] = uuid.UUID(resp.json()["id"])
    await set_org_context(db_session, org_id)
    return org_id, positions


async def _count(db_session, model):
    return await db_session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_a_run_saves_only_the_real_pick_and_records_the_spend(client, db_session, monkeypatch):
    """P1 is real, P9 is invented: one pending suggestion, one usage row on the FAST model."""
    org_id, positions = await _org_with_operations(client, db_session, "gen_run1@example.com")
    seen = _fake_anthropic(
        monkeypatch,
        usage=_usage(),
        parsed_output=CriticalPositionAnswer(picks=[_pick("P1"), _pick("P9")]),
    )

    created = await generate_critical_position_suggestions(db_session, org_id)

    assert len(created) == 1
    suggestion = created[0]
    assert suggestion.position_id in positions.values()
    assert (suggestion.suggestion_type, suggestion.status) == ("critical_position", "pending")
    assert (suggestion.suggested_criticality_type, suggestion.suggested_risk_level) == (
        "operational",
        "high",
    )
    # What Claude was shown: the department with its labelled positions.
    shown = seen["messages"][0]["content"]
    assert "Department: Operations" in shown
    assert "P1:" in shown and "P2:" in shown
    # The spend is recorded against the cheap tier.
    usage_row = (await db_session.scalars(select(AIUsageLog))).one()
    assert usage_row.model == settings.anthropic_model_fast
    assert usage_row.purpose == AIUsagePurpose.AI_SUGGESTION_GENERATION.value


@pytest.mark.asyncio
async def test_running_again_creates_nothing_new(client, db_session, monkeypatch):
    """The same answer twice: the second run is a quiet no-op (still paid for, though)."""
    org_id, _ = await _org_with_operations(client, db_session, "gen_run2@example.com")
    _fake_anthropic(
        monkeypatch,
        usage=_usage(),
        parsed_output=CriticalPositionAnswer(picks=[_pick("P1")]),
    )

    first = await generate_critical_position_suggestions(db_session, org_id)
    second = await generate_critical_position_suggestions(db_session, org_id)

    assert len(first) == 1
    assert second == []
    assert await _count(db_session, AISuggestion) == 1
    assert await _count(db_session, AIUsageLog) == 2


@pytest.mark.asyncio
async def test_nothing_to_ask_about_means_claude_is_never_called(client, db_session, monkeypatch):
    """No critical department: no candidates, no API call, no usage row."""
    owner = await register_verified_and_login(client, email="gen_run3@example.com")
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    seen = _fake_anthropic(
        monkeypatch, usage=_usage(), parsed_output=CriticalPositionAnswer(picks=[])
    )

    created = await generate_critical_position_suggestions(db_session, org_id)

    assert created == []
    assert seen == {}
    assert await _count(db_session, AIUsageLog) == 0
