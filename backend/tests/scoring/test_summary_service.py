"""Tests for writing, replacing and freezing the executive summary (M12 slice G). The model is faked.

Saved department rows are inserted directly: Q2 (1 April to 30 June) and Q3 (1 July to 30 September),
Dispatch (share 60) and Sales (share 40), 13 valid tasks in Q3.
"""
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import update

import app.modules.scoring.summary_generation as generation
from app.core.celery_app import celery
from app.modules.scoring import tasks as scoring_jobs
from app.modules.scoring.models import DepartmentScore, ExecutiveSummary
from app.modules.scoring.summary_service import ExecutiveSummaryService
from app.modules.scoring.summary_generation import SummaryDraft
from tests.conftest import set_org_context
from tests.scoring.test_employee_scores import _two_kpis
from tests.tasks.test_task_blocks_table import _block
from tests.tasks.test_tasks_for_scoring import _task, at
from tests.tasks.test_tasks_router import _world

Q2 = (date(2026, 4, 1), date(2026, 6, 30))
Q3 = (date(2026, 7, 1), date(2026, 9, 30))
MID_Q3 = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)  # the current quarter is Q3, the one before is Q2
MID_Q4 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)  # the current quarter is Q4, the one before is Q3


def _row(w, department_id, days, goals, share, on_time, late, not_done, punctuality, frozen=False):
    """One saved department row."""
    return DepartmentScore(
        organization_id=uuid.UUID(w.owner["organization"]["id"]),
        department_id=uuid.UUID(department_id),
        period_start=days[0],
        period_end=days[1],
        kpi_results_score=Decimal(goals),
        kpis_counted=1,
        kpis_expected=1,
        punctuality_on_time=on_time,
        punctuality_late=late,
        punctuality_not_done=not_done,
        punctuality_score=Decimal(punctuality),
        revenue_allocation_percentage=Decimal(share),
        finalized_at=datetime(2026, 10, 1, tzinfo=UTC) if frozen else None,
    )


async def _company(client, monkeypatch, db_session, tag, q3_valid_tasks=(6, 2, 2), q3_frozen=False):
    """Dispatch (6/2/2 tasks in Q3 unless told) and Sales (3 on time), with Q2 behind them."""
    w = await _world(client, monkeypatch, tag)
    await set_org_context(db_session, w.owner["organization"]["id"])
    on_time, late, not_done = q3_valid_tasks
    db_session.add_all([
        _row(w, w.dispatch, Q2, "75", "60", 5, 3, 2, "70", frozen=True),
        _row(w, w.sales, Q2, "80", "40", 2, 0, 0, "100", frozen=True),
        _row(w, w.dispatch, Q3, "70", "60", on_time, late, not_done, "60", frozen=q3_frozen),
        _row(w, w.sales, Q3, "90", "40", 3, 0, 0, "100", frozen=q3_frozen),
    ])
    await db_session.flush()
    return w


def facts_in(prompt: str) -> dict:
    """The fact sheet out of the prompt the model was shown."""
    return json.loads(prompt.split("Fact sheet:\n")[1].split("\n\nYour previous")[0])


def fake_model(monkeypatch, answer=None):
    """Fake the model. By default it writes a truthful sentence from the sheet it is shown.

    Returns the list of prompts seen. ``answer`` may be a function of the prompt.
    """
    prompts = []

    async def fake(db, **kwargs):
        prompts.append(kwargs["prompt"])
        if answer is not None:
            return SummaryDraft(text=answer(kwargs["prompt"]))
        company = facts_in(kwargs["prompt"])["company"]
        return SummaryDraft(text=f"The company scored {company['headline']} and punctuality is {company['punctuality']}.")

    monkeypatch.setattr(generation, "generate_structured", fake)
    return prompts


async def _saved(db_session, w, days) -> ExecutiveSummary | None:
    """The organization's saved summary for the period, read fresh."""
    from sqlalchemy import select
    stmt = select(ExecutiveSummary).where(
        ExecutiveSummary.organization_id == uuid.UUID(w.owner["organization"]["id"]),
        ExecutiveSummary.period_start == days[0],
    ).execution_options(populate_existing=True)
    return (await db_session.execute(stmt)).scalar_one_or_none()


def service(db_session):
    """The service under test."""
    return ExecutiveSummaryService(db_session)


@pytest.mark.asyncio
async def test_a_so_far_summary_is_written_from_the_fact_sheet_and_saved(client, monkeypatch, db_session):
    """Headline 78 (up 1 on Q2's 77), written by the model, source ai, not frozen."""
    w = await _company(client, monkeypatch, db_session, "sv1")
    prompts = fake_model(monkeypatch)

    result = await service(db_session).refresh_current(uuid.UUID(w.owner["organization"]["id"]), MID_Q3)

    assert result == "written" and len(prompts) == 1
    sheet = facts_in(prompts[0])
    assert sheet["period"] == "the quarter so far"
    assert (sheet["company"]["headline"], sheet["company"]["headline_change"]) == (78, 1)
    assert [d["name"] for d in sheet["departments"]] == ["Dispatch", "Sales"]
    saved = await _saved(db_session, w, Q3)
    assert saved.source == "ai" and saved.finalized_at is None
    assert saved.summary_text == "The company scored 78 and punctuality is 76.9."


@pytest.mark.asyncio
async def test_an_unchanged_week_makes_no_model_call_and_a_changed_one_replaces_the_text(client, monkeypatch, db_session):
    """Same facts: 'unchanged' and still one call in total. Sales' result moves: written again, text replaced."""
    w = await _company(client, monkeypatch, db_session, "sv2")
    prompts = fake_model(monkeypatch)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await service(db_session).refresh_current(org_id, MID_Q3)

    assert await service(db_session).refresh_current(org_id, MID_Q3) == "unchanged"
    assert len(prompts) == 1

    await db_session.execute(
        update(DepartmentScore)
        .where(DepartmentScore.department_id == uuid.UUID(w.sales), DepartmentScore.period_start == Q3[0])
        .values(kpi_results_score=Decimal("50"))
    )
    assert await service(db_session).refresh_current(org_id, MID_Q3) == "written"
    assert len(prompts) == 2
    assert (await _saved(db_session, w, Q3)).summary_text == "The company scored 62 and punctuality is 76.9."


@pytest.mark.asyncio
async def test_fewer_than_ten_valid_tasks_means_no_model_call_and_nothing_saved(client, monkeypatch, db_session):
    """Dispatch 2/2/2 plus Sales' 3 is 9 valid tasks, one short of the 10 needed, so no summary."""
    w = await _company(client, monkeypatch, db_session, "sv3", q3_valid_tasks=(2, 2, 2))
    prompts = fake_model(monkeypatch)

    result = await service(db_session).refresh_current(uuid.UUID(w.owner["organization"]["id"]), MID_Q3)

    assert result == "not_enough_data" and prompts == []
    assert await _saved(db_session, w, Q3) is None


@pytest.mark.asyncio
async def test_a_model_that_keeps_getting_numbers_wrong_leaves_the_plain_facts(client, monkeypatch, db_session):
    """Two wrong answers: the plain fallback is saved, marked plain, after exactly two calls."""
    w = await _company(client, monkeypatch, db_session, "sv4")
    prompts = fake_model(monkeypatch, answer=lambda prompt: "Sales fell 41 points.")

    result = await service(db_session).refresh_current(uuid.UUID(w.owner["organization"]["id"]), MID_Q3)

    assert result == "written" and len(prompts) == 2
    saved = await _saved(db_session, w, Q3)
    assert saved.source == "plain" and saved.summary_text.startswith("Company score 78 (+1)")


@pytest.mark.asyncio
async def test_the_closed_quarter_gets_one_final_frozen_summary(client, monkeypatch, db_session):
    """Q3 is frozen: the final summary is written once, frozen, and a second run changes nothing."""
    w = await _company(client, monkeypatch, db_session, "sv5", q3_frozen=True)
    prompts = fake_model(monkeypatch)
    org_id = uuid.UUID(w.owner["organization"]["id"])

    assert await service(db_session).finalize_previous(org_id, MID_Q4) == "finalized"
    assert facts_in(prompts[0])["period"] == "the quarter that has ended"
    saved = await _saved(db_session, w, Q3)
    assert saved.finalized_at is not None

    assert await service(db_session).finalize_previous(org_id, MID_Q4) == "already_final"
    assert len(prompts) == 1
    # And a "so far" run for that same (now frozen) quarter cannot touch it.
    assert await service(db_session).refresh_current(org_id, MID_Q3) == "frozen"


@pytest.mark.asyncio
async def test_a_quarter_whose_scores_are_not_closed_yet_gets_no_final_summary(client, monkeypatch, db_session):
    """Q3 rows still running: finalising waits until the scores themselves are closed."""
    w = await _company(client, monkeypatch, db_session, "sv6", q3_frozen=False)
    prompts = fake_model(monkeypatch)

    result = await service(db_session).finalize_previous(uuid.UUID(w.owner["organization"]["id"]), MID_Q4)

    assert result == "period_not_closed" and prompts == []


@pytest.mark.asyncio
async def test_the_weekly_job_for_one_organization_does_both_steps_in_order(client, monkeypatch, db_session):
    """Just after Q3 closed: Q3's final summary is written and frozen; Q4 has no data yet."""
    w = await _company(client, monkeypatch, db_session, "sv8", q3_frozen=True)
    fake_model(monkeypatch)
    org_id = w.owner["organization"]["id"]

    result = await scoring_jobs.run_summary_for_organization(db_session, uuid.UUID(org_id), MID_Q4)

    assert result == {"final": "finalized", "current": "not_enough_data"}
    assert (await _saved(db_session, w, Q3)).finalized_at is not None


@pytest.mark.asyncio
async def test_the_weekly_scan_queues_a_summary_job_for_organizations_with_something_to_score(
    client, monkeypatch, db_session
):
    """Only the company with a KPI is queued, and with the summary task's name."""
    with_kpi = await _world(client, monkeypatch, "sv9")
    nothing = await _world(client, monkeypatch, "sv9b")
    await _two_kpis(client, with_kpi)
    sent = MagicMock()
    monkeypatch.setattr(celery, "send_task", sent)

    await set_org_context(db_session, "")
    queued = await scoring_jobs.run_summary_scan(db_session)

    calls = sent.call_args_list
    queued_ids = {call.kwargs["args"][0] for call in calls}
    assert queued == len(calls) and queued >= 1
    assert all(call.args[0] == scoring_jobs.SUMMARY_ORG_TASK for call in calls)
    assert with_kpi.owner["organization"]["id"] in queued_ids
    assert nothing.owner["organization"]["id"] not in queued_ids


def test_the_weekly_job_is_registered_and_scheduled_for_monday_three_utc():
    """Celery knows both summary tasks, and Beat runs the scan on Mondays at 03:00."""
    entry = celery.conf.beat_schedule["scoring-summary-weekly"]

    assert entry["task"] == scoring_jobs.SUMMARY_WEEKLY_TASK
    assert (entry["schedule"]._orig_day_of_week, entry["schedule"]._orig_hour, entry["schedule"]._orig_minute) == (
        "monday", 3, 0,
    )
    assert scoring_jobs.SUMMARY_WEEKLY_TASK in celery.tasks and scoring_jobs.SUMMARY_ORG_TASK in celery.tasks


@pytest.mark.asyncio
async def test_delays_are_counted_by_department_and_reason_and_no_person_is_named(client, monkeypatch, db_session):
    """Two Dispatch tasks held back awaiting another department show as a count; the prompt has no employee names."""
    w = await _company(client, monkeypatch, db_session, "sv7")
    tasks = [_task(w, "one"), _task(w, "two")]
    db_session.add_all(tasks)
    await db_session.flush()
    for task in tasks:
        db_session.add(_block(
            w.owner["organization"]["id"], str(task.id), w.owner["user"]["id"],
            review_status="approved", blocked_at=at(8, 10), unblocked_at=at(8, 12),
            reviewed_by_user_id=uuid.UUID(w.owner["user"]["id"]), reviewed_at=at(8, 13),
        ))
    await db_session.flush()
    prompts = fake_model(monkeypatch)

    await service(db_session).refresh_current(uuid.UUID(w.owner["organization"]["id"]), MID_Q3)

    assert facts_in(prompts[0])["delays_by_reason"] == [
        {"department": "Dispatch", "reason": "awaiting_other_department", "held_back_tasks": 2}
    ]
    for name in ("Chidi", "Bola", "Tunde", "Dana", "Sam", "Tester"):
        assert name not in prompts[0]
