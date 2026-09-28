"""The missing-department chain: the per-run cap, then the whole run.

Scenario: Kelechi's company is missing "Legal". Claude — faked here —
proposes it, and it lands in the queue as a name, not a real department:
nothing is created until HR approves it.
"""
import uuid

import pytest
from sqlalchemy import func, select

from tests.ai.test_llm_generate_structured import _fake_anthropic, _usage
from tests.conftest import register_verified_and_login, set_org_context
from app.core.config import settings
from app.modules.ai.enums import AIUsagePurpose
from app.modules.ai.generation import (
    generate_missing_department_suggestions,
    select_missing_department_picks,
)
from app.modules.ai.models import AISuggestion, AIUsageLog
from app.modules.ai.schemas import MissingDepartmentAnswer, MissingDepartmentPick


def _pick(name, rationale="No department owns this yet."):
    return MissingDepartmentPick(department_name=name, rationale=rationale)


# ------------------------------------------------- select_missing_department_picks (pure)

def test_the_cap_keeps_only_the_first_n_in_claudes_own_order(monkeypatch):
    """Cap 2: Legal and Compliance kept, Innovation Lab dropped."""
    monkeypatch.setattr(settings, "ai_max_missing_departments_per_run", 2)
    picks = [_pick("Legal"), _pick("Compliance"), _pick("Innovation Lab")]

    kept = select_missing_department_picks(picks)

    assert [p.department_name for p in kept] == ["Legal", "Compliance"]


def test_no_picks_means_nothing_selected():
    """Claude finding nothing missing is a valid answer."""
    assert select_missing_department_picks([]) == []


def test_fewer_than_the_cap_are_all_kept(monkeypatch):
    """Nothing to trim when the answer is already under the limit."""
    monkeypatch.setattr(settings, "ai_max_missing_departments_per_run", 5)
    picks = [_pick("Legal")]

    assert select_missing_department_picks(picks) == picks


# --------------------------------------------------------------- the whole run

async def _org(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    return org_id


async def _count(db_session, model):
    return await db_session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_a_run_saves_the_proposed_name_on_the_strong_model(client, db_session, monkeypatch):
    """A pending suggestion is created with the name only — no department row exists yet."""
    org_id = await _org(client, db_session, "miss_run1@example.com")
    seen = _fake_anthropic(
        monkeypatch, usage=_usage(), parsed_output=MissingDepartmentAnswer(picks=[_pick("Legal")])
    )

    created = await generate_missing_department_suggestions(db_session, org_id)

    assert len(created) == 1
    suggestion = created[0]
    assert (suggestion.suggestion_type, suggestion.status) == ("missing_department", "pending")
    assert suggestion.suggested_department_name == "Legal"
    assert suggestion.department_id is None
    usage_row = (await db_session.scalars(select(AIUsageLog))).one()
    assert usage_row.model == settings.anthropic_model_strong
    assert usage_row.purpose == AIUsagePurpose.AI_SUGGESTION_GENERATION.value
    assert seen["output_format"] is MissingDepartmentAnswer


@pytest.mark.asyncio
async def test_running_again_creates_nothing_new(client, db_session, monkeypatch):
    """The same proposed name twice: the second run is a quiet no-op."""
    org_id = await _org(client, db_session, "miss_run2@example.com")
    _fake_anthropic(
        monkeypatch, usage=_usage(), parsed_output=MissingDepartmentAnswer(picks=[_pick("Legal")])
    )

    first = await generate_missing_department_suggestions(db_session, org_id)
    second = await generate_missing_department_suggestions(db_session, org_id)

    assert len(first) == 1
    assert second == []
    assert await _count(db_session, AISuggestion) == 1
    assert await _count(db_session, AIUsageLog) == 2


@pytest.mark.asyncio
async def test_a_brand_new_org_still_gets_a_real_run(client, db_session, monkeypatch):
    """No departments at all — the one type with no 'nothing to ask about' skip."""
    org_id = await _org(client, db_session, "miss_run3@example.com")
    seen = _fake_anthropic(
        monkeypatch, usage=_usage(), parsed_output=MissingDepartmentAnswer(picks=[])
    )

    created = await generate_missing_department_suggestions(db_session, org_id)

    assert created == []
    assert seen != {}  # Claude was actually asked, unlike the other two types
    assert await _count(db_session, AIUsageLog) == 1
