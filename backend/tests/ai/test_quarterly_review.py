"""The Quarterly Objective Review Beat job: who it enqueues, and how it's scheduled.

Scenario: it's the 1st of the month, 1am UTC. Beat fires this job. Two
orgs' fiscal quarters just turned over; a third's turned over two months
ago. Only the first two should get a fresh generation run enqueued —
without this job ever touching an LLM itself, or seeing anything about
any organization beyond its id and fiscal month.

The cross-tenant repository call is faked throughout (it depends on a SQL
function introduced in a migration this session couldn't write — see
08_DECISIONS.md 2026-09-27 — so these tests exercise everything *around*
that call, not the call itself).
"""
import uuid

import pytest

import app.modules.ai.tasks as ai_tasks
from tests.conftest import register_verified_and_login
from app.core.celery_app import celery
from app.modules.ai.tasks import (
    QUARTERLY_REVIEW_TASK,
    _QUARTERLY_REVIEW_LOOKBACK,
    quarterly_objective_review,
    run_quarterly_review,
)
from app.modules.tenancy_identity.repository import OrganizationRepository


def _fake_org_list(monkeypatch, orgs: list[tuple[uuid.UUID, int]]):
    async def fake(self):
        return orgs

    monkeypatch.setattr(OrganizationRepository, "list_fiscal_months_for_quarterly_review", fake)


def _fake_send_task(monkeypatch):
    sent = []
    monkeypatch.setattr(celery, "send_task", lambda name, args: sent.append((name, args)))
    return sent


def _fake_due_months(monkeypatch, due_months: set[int]):
    """Decide "due" by fiscal month alone, decoupled from the real calendar date.

    The date math itself (is_due_for_quarterly_review) already has its own
    dedicated, calendar-exact tests in tests/core/test_fiscal.py — this
    file is about the orchestration around it (which orgs get enqueued),
    not a second copy of that math tied to whatever day these tests run.
    """
    monkeypatch.setattr(
        ai_tasks,
        "is_due_for_quarterly_review",
        lambda fiscal_year_start_month, now, lookback: fiscal_year_start_month in due_months,
    )


@pytest.mark.asyncio
async def test_only_due_orgs_are_enqueued(monkeypatch, db_session):
    """Two due, one not — only the due ones get a generation run enqueued."""
    due_a, due_b, not_due = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _fake_org_list(monkeypatch, [(due_a, 1), (due_b, 4), (not_due, 7)])
    _fake_due_months(monkeypatch, {1, 4})
    sent = _fake_send_task(monkeypatch)

    count = await run_quarterly_review(db_session)

    assert count == 2
    assert {name for name, _ in sent} == {"app.modules.ai.tasks.generate_suggestions"}
    assert {args[0] for _, args in sent} == {str(due_a), str(due_b)}


@pytest.mark.asyncio
async def test_no_orgs_due_means_nothing_enqueued(monkeypatch, db_session):
    """Not one org's quarter turned over — a quiet, empty run, not an error."""
    _fake_org_list(monkeypatch, [(uuid.uuid4(), 6)])
    _fake_due_months(monkeypatch, set())
    sent = _fake_send_task(monkeypatch)

    count = await run_quarterly_review(db_session)

    assert count == 0
    assert sent == []


@pytest.mark.asyncio
async def test_no_organizations_at_all_is_not_an_error(monkeypatch, db_session):
    """An empty platform (or every org mid-quarter) is a valid, harmless outcome."""
    _fake_org_list(monkeypatch, [])
    sent = _fake_send_task(monkeypatch)

    assert await run_quarterly_review(db_session) == 0
    assert sent == []


@pytest.mark.asyncio
async def test_the_real_cross_tenant_function_returns_a_freshly_created_org(client, db_session):
    """No fake here: the real SECURITY DEFINER function, called with no tenant context set.

    Proves the actual escape hatch works end-to-end (08_DECISIONS.md
    2026-09-27/28) — not just the orchestration around a faked version of
    it, which is what every other test in this file exercises.
    """
    owner = await register_verified_and_login(client, email="qreview_real1@example.com")
    org_id = uuid.UUID(owner["organization"]["id"])

    orgs = await OrganizationRepository(db_session).list_fiscal_months_for_quarterly_review()

    matching = [month for oid, month in orgs if oid == org_id]
    assert matching == [1]  # the default fiscal_year_start_month


def test_the_lookback_exceeds_the_daily_schedule_interval():
    """If the lookback were <= 24h, a boundary landing between two daily runs could be missed."""
    assert _QUARTERLY_REVIEW_LOOKBACK.total_seconds() > 24 * 3600


def test_the_task_name_is_the_one_the_beat_schedule_points_at():
    """The Beat schedule entry and the task's registered name must agree exactly."""
    assert QUARTERLY_REVIEW_TASK in celery.tasks
    assert celery.tasks[QUARTERLY_REVIEW_TASK].name == QUARTERLY_REVIEW_TASK
    assert celery.conf.beat_schedule["quarterly-objective-review"]["task"] == QUARTERLY_REVIEW_TASK


def test_quarterly_objective_review_is_the_registered_celery_task():
    """The Python function and the registered task are the same object, not a stale copy."""
    assert quarterly_objective_review.name == QUARTERLY_REVIEW_TASK
