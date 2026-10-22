"""Tests for the nightly scoring job (M12 slice D): closing a quarter once, refreshing the open one.

Dates are in 2026 and the default organization works on Lagos time (UTC+1) with
a calendar fiscal year, so Q3 runs from 1 July to 30 September and Q4 from 1 October.
"""
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, update

from app.core.celery_app import celery
from app.modules.kpis.models import KPIScore
from app.modules.scoring import tasks as scoring_jobs
from app.modules.scoring.models import DepartmentScore
from app.modules.tenancy_identity.models import Organization
from tests.conftest import set_org_context
from tests.scoring.test_department_scores import _save_kpi_result
from tests.scoring.test_employee_scores import _done, _rows, _task, _two_kpis, at
from tests.tasks.test_tasks_router import KPIS, _world

Q3_FIRST_DAY, Q4_FIRST_DAY = date(2026, 7, 1), date(2026, 10, 1)
JUST_AFTER_Q3 = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)  # 02:00 in Lagos on 1 October: Q3 has just ended


async def _old_company(db_session, w, created=datetime(2026, 1, 15, tzinfo=UTC)) -> None:
    """Make the company older than the quarter under test (the job only closes quarters a company lived through)."""
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(update(Organization).where(Organization.id == org_id).values(created_at=created))


async def _night(db_session, w, now) -> dict:
    """Run the per-organization job the way Celery would."""
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    return await scoring_jobs.run_scoring_for_organization(db_session, uuid.UUID(org_id), now)


async def _department(db_session, department_id: str, period_start: date) -> DepartmentScore | None:
    """A department's saved row for a period, read fresh from the database (or None)."""
    stmt = (
        select(DepartmentScore)
        .where(DepartmentScore.department_id == uuid.UUID(department_id), DepartmentScore.period_start == period_start)
        .execution_options(populate_existing=True)
    )
    return (await db_session.execute(stmt)).scalar_one_or_none()


async def _kpi_result(db_session, kpi_id: str, period_start: date) -> KPIScore | None:
    """The result saved for a KPI in a period, read fresh (or None)."""
    stmt = (
        select(KPIScore)
        .where(KPIScore.kpi_id == uuid.UUID(kpi_id), KPIScore.period_start == period_start)
        .execution_options(populate_existing=True)
    )
    return (await db_session.execute(stmt)).scalar_one_or_none()


async def _task_count_kpi(client, w, name: str, weight: int, target: int) -> str:
    """A KPI tracked by counting completed tasks, with a target."""
    created = await client.post(
        KPIS,
        json={
            "department_id": w.dispatch, "name": name, "weight": weight,
            "tracking_mode": "task_count", "target_value": target,
        },
        headers=w.hr,
    )
    assert created.status_code == 200
    return created.json()["id"]


@pytest.mark.asyncio
async def test_the_first_night_after_a_quarter_closes_it_and_the_next_night_leaves_it_alone(
    client, monkeypatch, db_session
):
    """Q3 is frozen on 1 October (people and departments), Q4 stays a running figure, and a second night changes nothing."""
    w = await _world(client, monkeypatch, "nj1")
    lead_follow_up, _ = await _two_kpis(client, w)
    await _old_company(db_session, w)
    db_session.add(_task(w, "on time", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))))
    await db_session.flush()
    await _save_kpi_result(db_session, w, lead_follow_up, "70")

    first = await _night(db_session, w, JUST_AFTER_Q3)
    chidi_q3 = (await _rows(db_session, w.chidi.employee_id, Q3_FIRST_DAY))[0]
    dispatch_q3 = await _department(db_session, w.dispatch, Q3_FIRST_DAY)
    dispatch_q4 = await _department(db_session, w.dispatch, Q4_FIRST_DAY)
    frozen_at = (chidi_q3.finalized_at, dispatch_q3.finalized_at)
    second = await _night(db_session, w, JUST_AFTER_Q3 + timedelta(days=1))

    assert first == {"closed_previous_period": True} and second == {"closed_previous_period": False}
    assert chidi_q3.finalized_at is not None
    assert (chidi_q3.tasks_on_time, chidi_q3.score_percentage) == (1, Decimal("100.00"))
    assert dispatch_q3.finalized_at is not None
    assert (dispatch_q3.kpi_results_score, dispatch_q3.kpis_counted, dispatch_q3.kpis_expected) == (Decimal("70.00"), 1, 2)
    assert dispatch_q3.punctuality_score == Decimal("100.00")
    assert dispatch_q4 is not None and dispatch_q4.finalized_at is None  # the open quarter keeps running
    assert (await _rows(db_session, w.chidi.employee_id, Q3_FIRST_DAY))[0].finalized_at == frozen_at[0]
    assert (await _department(db_session, w.dispatch, Q3_FIRST_DAY)).finalized_at == frozen_at[1]


@pytest.mark.asyncio
async def test_a_job_that_runs_days_late_still_judges_the_quarter_at_its_end(client, monkeypatch, db_session):
    """Due 20 Sept, finished on 3 Oct, job run on 5 Oct: Q3's final card says not done, as it would have on 1 Oct."""
    w = await _world(client, monkeypatch, "nj2")
    lead_follow_up, _ = await _two_kpis(client, w)
    await _old_company(db_session, w)
    db_session.add(_task(w, "late finisher", lead_follow_up, w.chidi.employee_id, **_done(at(9, 20), at(10, 3))))
    await db_session.flush()

    await _night(db_session, w, datetime(2026, 10, 5, 1, 0, tzinfo=UTC))

    row = (await _rows(db_session, w.chidi.employee_id, Q3_FIRST_DAY))[0]
    assert (row.tasks_on_time, row.tasks_late, row.tasks_not_done) == (0, 0, 1)
    assert row.finalized_at is not None


@pytest.mark.asyncio
async def test_a_company_that_did_not_exist_yet_gets_no_frozen_quarter(client, monkeypatch, db_session):
    """Created on 20 October: nothing closes for Q3, and only the running Q4 rows exist."""
    w = await _world(client, monkeypatch, "nj3")
    await _two_kpis(client, w)
    await _old_company(db_session, w, created=datetime(2026, 10, 20, tzinfo=UTC))

    result = await _night(db_session, w, datetime(2026, 10, 21, 1, 0, tzinfo=UTC))

    assert result == {"closed_previous_period": False}
    assert await _department(db_session, w.dispatch, Q3_FIRST_DAY) is None
    q4 = await _department(db_session, w.dispatch, Q4_FIRST_DAY)
    assert q4 is not None and q4.finalized_at is None


@pytest.mark.asyncio
async def test_a_task_count_kpi_gets_its_result_saved_and_the_department_headline_reads_it(
    client, monkeypatch, db_session
):
    """14 completed tasks against a target of 20 is 70%: saved for Q3 at close, and the department headline is 70."""
    w = await _world(client, monkeypatch, "nj4")
    deals = await _task_count_kpi(client, w, "Close 20 deals", weight=100, target=20)
    await _old_company(db_session, w)
    for n in range(14):
        db_session.add(
            _task(w, f"deal {n}", deals, w.chidi.employee_id, **_done(at(8, 1), at(7, 20), due_at=None))
        )
    await db_session.flush()

    await _night(db_session, w, JUST_AFTER_Q3)

    q3 = await _kpi_result(db_session, deals, Q3_FIRST_DAY)
    q4 = await _kpi_result(db_session, deals, Q4_FIRST_DAY)
    dispatch = await _department(db_session, w.dispatch, Q3_FIRST_DAY)
    assert (q3.actual_value, q3.score_percentage) == (Decimal("14.00"), Decimal("70.00"))
    assert (q4.actual_value, q4.score_percentage) == (Decimal("0.00"), Decimal("0.00"))  # the running Q4 so far
    assert (dispatch.kpi_results_score, dispatch.kpis_counted, dispatch.kpis_expected) == (Decimal("70.00"), 1, 1)


@pytest.mark.asyncio
async def test_a_task_count_kpi_far_above_its_target_is_capped_instead_of_crashing_the_night(
    client, monkeypatch, db_session
):
    """10 completed tasks against a target of 1 is 1000%: capped at 999.99, the most the column can hold."""
    w = await _world(client, monkeypatch, "nj5")
    calls = await _task_count_kpi(client, w, "Calls", weight=100, target=1)
    await _old_company(db_session, w)
    for n in range(10):
        db_session.add(_task(w, f"call {n}", calls, w.chidi.employee_id, **_done(None, at(8, 1), due_at=None)))
    await db_session.flush()

    await _night(db_session, w, JUST_AFTER_Q3)

    q3 = await _kpi_result(db_session, calls, Q3_FIRST_DAY)
    assert (q3.actual_value, q3.score_percentage) == (Decimal("10.00"), Decimal("999.99"))


@pytest.mark.asyncio
async def test_typed_in_kpis_are_never_overwritten_by_the_job(client, monkeypatch, db_session):
    """A manual KPI's result stays exactly what HR typed, before and after the close."""
    w = await _world(client, monkeypatch, "nj6")
    lead_follow_up, _ = await _two_kpis(client, w)
    await _old_company(db_session, w)
    await _save_kpi_result(db_session, w, lead_follow_up, "70")

    await _night(db_session, w, JUST_AFTER_Q3)

    typed = await _kpi_result(db_session, lead_follow_up, Q3_FIRST_DAY)
    assert (typed.actual_value, typed.score_percentage) == (Decimal("70.00"), Decimal("70.00"))
    assert await _kpi_result(db_session, lead_follow_up, Q4_FIRST_DAY) is None  # nothing was invented for Q4


@pytest.mark.asyncio
async def test_the_scan_queues_one_job_per_organization_that_can_have_a_score(client, monkeypatch, db_session):
    """An organization with a KPI is queued; one with nothing to score is not."""
    with_kpi = await _world(client, monkeypatch, "nj7")
    nothing = await _world(client, monkeypatch, "nj8")
    await _two_kpis(client, with_kpi)
    sent = MagicMock()
    monkeypatch.setattr(celery, "send_task", sent)

    await set_org_context(db_session, "")
    queued = await scoring_jobs.run_scoring_scan(db_session)

    calls = sent.call_args_list
    # Each call looks like: send_task("<task name>", args=["<organization id>"]).
    queued_ids = {call.kwargs["args"][0] for call in calls}
    assert queued == len(calls) and queued >= 1
    assert all(call.args[0] == scoring_jobs.SCORE_ORG_TASK for call in calls)
    assert with_kpi.owner["organization"]["id"] in queued_ids
    assert nothing.owner["organization"]["id"] not in queued_ids


def test_the_nightly_job_is_registered_and_scheduled_for_two_in_the_morning_utc():
    """Celery knows both tasks, and Beat runs the scan at 02:00."""
    import app.modules.scoring.tasks  # noqa: F401 - importing registers the tasks

    entry = celery.conf.beat_schedule["scoring-nightly"]

    assert scoring_jobs.SCORING_NIGHTLY_TASK in celery.tasks and scoring_jobs.SCORE_ORG_TASK in celery.tasks
    assert entry["task"] == scoring_jobs.SCORING_NIGHTLY_TASK
    assert (entry["schedule"].hour, entry["schedule"].minute) == ({2}, {0})
