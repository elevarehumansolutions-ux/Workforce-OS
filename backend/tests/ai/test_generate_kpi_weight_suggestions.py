"""The kpi_weight chain: filtering Claude's picks, then the whole run.

Covers the sum-to-100 tolerance check specific to this chain. Scenario:
Adaeze's Sales department has two KPIs. Claude — faked here — proposes a
weight split; only a real, complete (summing to ~100) answer reaches the
review queue.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.ai.test_llm_generate_structured import _fake_anthropic, _usage
from tests.conftest import register_verified_and_login, set_org_context
from app.core.config import settings
from app.modules.ai.generation import (
    KPIWeightGroupContext,
    generate_kpi_weight_suggestions,
    select_kpi_weight_picks,
)
from app.modules.ai.llm import LLMOutputError
from app.modules.ai.models import AISuggestion, AIUsageLog
from app.modules.ai.schemas import KPIWeightAnswer, KPIWeightPick

KPIS = "/api/v1/kpis"
DEPARTMENTS = "/api/v1/departments"


def _pick(handle, weight="50"):
    return KPIWeightPick(handle=handle, suggested_weight=Decimal(weight), rationale="Core to this team's work.")


def _context(handle_count):
    kpi_ids = [uuid.uuid4() for _ in range(handle_count)]
    return KPIWeightGroupContext(
        department_id=uuid.uuid4(),
        department_name="Sales",
        location_id=None,
        kpis=[],
        handles={f"K{n}": kid for n, kid in enumerate(kpi_ids, start=1)},
    )


def _ids_kept(picks, context):
    return {kid for kid, _ in select_kpi_weight_picks(picks, context)}


# ------------------------------------------------------- select_kpi_weight_picks (pure)

def test_a_valid_two_kpi_split_is_kept_in_full():
    """K1=50, K2=50 sums to exactly 100: both kept."""
    context = _context(2)
    kept = select_kpi_weight_picks([_pick("K1", "50"), _pick("K2", "50")], context)
    assert len(kept) == 2


def test_an_invented_handle_is_dropped_but_the_group_still_balances():
    """K9 was never handed out and is dropped; the real two still sum to 100."""
    context = _context(2)
    kept_ids = _ids_kept([_pick("K1", "50"), _pick("K2", "50"), _pick("K9", "1")], context)
    assert kept_ids == {context.handles["K1"], context.handles["K2"]}


def test_a_group_whose_resolved_total_drifts_from_100_is_dropped_entirely():
    """K1=50, K2=20 only sums to 70: the whole group's picks are dropped, not half-applied."""
    context = _context(2)
    assert select_kpi_weight_picks([_pick("K1", "50"), _pick("K2", "20")], context) == []


def test_a_tiny_rounding_drift_is_still_accepted():
    """99.7 is within the 0.5 tolerance of 100 — a rounding artifact, not a broken answer."""
    context = _context(2)
    kept = select_kpi_weight_picks([_pick("K1", "49.8"), _pick("K2", "49.9")], context)
    assert len(kept) == 2


def test_a_kpi_listed_twice_keeps_its_first_weight_and_still_must_balance():
    """The second, conflicting pick for the same KPI is dropped before the total is checked."""
    context = _context(1)
    kept = select_kpi_weight_picks([_pick("K1", "100"), _pick("K1", "40")], context)
    assert len(kept) == 1
    assert kept[0][1].suggested_weight == Decimal("100")


def test_mostly_invented_picks_fail_the_run():
    """Both picks point at KPIs that don't exist: unusable, not trimmed."""
    context = _context(1)
    with pytest.raises(LLMOutputError):
        select_kpi_weight_picks([_pick("K8"), _pick("K9")], context)


def test_no_picks_means_nothing_selected():
    """Claude proposing nothing for this group is a valid answer."""
    assert select_kpi_weight_picks([], _context(2)) == []


# --------------------------------------------------------- the whole run (DB + fake Claude)

async def _org_with_two_kpis(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    dept_id = dept.json()["id"]
    k1 = await client.post(KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 50}, headers=h)
    k2 = await client.post(KPIS, json={"department_id": dept_id, "name": "Pipeline value", "weight": 50}, headers=h)
    await set_org_context(db_session, org_id)
    return org_id, {uuid.UUID(k1.json()["id"]), uuid.UUID(k2.json()["id"])}


async def _count(db_session, model):
    return await db_session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_a_run_saves_both_real_picks_on_the_strong_model(client, db_session, monkeypatch):
    """A valid, balanced two-KPI answer creates two pending suggestions, priced on the strong tier."""
    org_id, kpi_ids = await _org_with_two_kpis(client, db_session, "kw_run1@example.com")
    seen = _fake_anthropic(
        monkeypatch, usage=_usage(),
        parsed_output=KPIWeightAnswer(picks=[_pick("K1", "40"), _pick("K2", "60")]),
    )

    created = await generate_kpi_weight_suggestions(db_session, org_id)

    assert len(created) == 2
    assert {s.kpi_id for s in created} == kpi_ids
    assert {s.suggested_weight for s in created} == {Decimal("40"), Decimal("60")}
    assert all((s.suggestion_type, s.status) == ("kpi_weight", "pending") for s in created)
    shown = seen["messages"][0]["content"]
    assert "K1:" in shown and "K2:" in shown and "Sales" in shown
    usage_row = (await db_session.scalars(select(AIUsageLog))).one()
    assert usage_row.model == settings.anthropic_model_strong


@pytest.mark.asyncio
async def test_running_again_creates_nothing_new(client, db_session, monkeypatch):
    """The same answer twice: the second run is a quiet no-op (still paid for, though)."""
    org_id, _ = await _org_with_two_kpis(client, db_session, "kw_run2@example.com")
    _fake_anthropic(
        monkeypatch, usage=_usage(),
        parsed_output=KPIWeightAnswer(picks=[_pick("K1", "40"), _pick("K2", "60")]),
    )

    first = await generate_kpi_weight_suggestions(db_session, org_id)
    second = await generate_kpi_weight_suggestions(db_session, org_id)

    assert len(first) == 2
    assert second == []
    assert await _count(db_session, AISuggestion) == 2
    assert await _count(db_session, AIUsageLog) == 2


@pytest.mark.asyncio
async def test_no_candidate_group_means_claude_is_never_called(client, db_session, monkeypatch):
    """A department with zero or one KPI has nothing to split: no API call, no usage row."""
    owner = await register_verified_and_login(client, email="kw_run3@example.com")
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    await client.post(KPIS, json={"department_id": dept.json()["id"], "name": "Only one", "weight": 100}, headers=h)
    await set_org_context(db_session, org_id)
    seen = _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=KPIWeightAnswer(picks=[]))

    created = await generate_kpi_weight_suggestions(db_session, org_id)

    assert created == []
    assert seen == {}
    assert await _count(db_session, AIUsageLog) == 0


@pytest.mark.asyncio
async def test_an_off_total_answer_creates_no_suggestions_but_still_logs_usage(client, db_session, monkeypatch):
    """A real candidate group exists (so Claude is called and paid for), but its answer doesn't balance."""
    org_id, _ = await _org_with_two_kpis(client, db_session, "kw_run4@example.com")
    _fake_anthropic(
        monkeypatch, usage=_usage(),
        parsed_output=KPIWeightAnswer(picks=[_pick("K1", "30"), _pick("K2", "30")]),
    )

    created = await generate_kpi_weight_suggestions(db_session, org_id)

    assert created == []
    assert await _count(db_session, AISuggestion) == 0
    assert await _count(db_session, AIUsageLog) == 1
