"""Tests for working out and saving a department's two numbers (M12 slice C part 2)."""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.modules.kpis.models import KPIScore
from app.modules.organization.models import Department
from app.modules.scoring.models import DepartmentScore
from app.modules.scoring.service import ScoringService
from app.modules.tasks.models import Task
from tests.conftest import set_org_context
from tests.scoring.test_employee_scores import _done, _task, _two_kpis, at
from tests.tasks.test_tasks_router import _world

Q3_START = datetime(2026, 7, 1, tzinfo=UTC)
Q4_START = datetime(2026, 10, 1, tzinfo=UTC)
Q3_FIRST_DAY, Q3_LAST_DAY = date(2026, 7, 1), date(2026, 9, 30)


async def _save_kpi_result(db_session, w, kpi_id: str, score: str) -> None:
    """Record the result a KPI has for Q3 (what HR types in, or what the task-count job will write)."""
    db_session.add(
        KPIScore(
            organization_id=uuid.UUID(w.owner["organization"]["id"]),
            kpi_id=uuid.UUID(kpi_id),
            period_start=Q3_FIRST_DAY,
            period_end=Q3_LAST_DAY,
            actual_value=Decimal(score),
            score_percentage=Decimal(score),
        )
    )
    await db_session.flush()


async def _compute(db_session, w, now=Q4_START) -> int:
    """Work out Q3's department scores the way the final write judges them."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    return await ScoringService(db_session).compute_department_scores(
        uuid.UUID(w.owner["organization"]["id"]), Q3_START, Q4_START, now
    )


async def _row(db_session, department_id: str) -> DepartmentScore:
    """The department's saved Q3 row, always read fresh from the database."""
    stmt = (
        select(DepartmentScore)
        .where(DepartmentScore.department_id == uuid.UUID(department_id), DepartmentScore.period_start == Q3_FIRST_DAY)
        .execution_options(populate_existing=True)
    )
    return (await db_session.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_the_headline_is_the_weighted_results_of_the_departments_kpis(client, monkeypatch, db_session):
    """Lead Follow-up 70% at weight 70 and Contract Paperwork 100% at weight 30 give 79.00, 2 of 2 KPIs."""
    w = await _world(client, monkeypatch, "ds1")
    lead_follow_up, paperwork = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    await _save_kpi_result(db_session, w, lead_follow_up, "70")
    await _save_kpi_result(db_session, w, paperwork, "100")

    await _compute(db_session, w)

    row = await _row(db_session, w.dispatch)
    assert row.kpi_results_score == Decimal("79.00")
    assert (row.kpis_counted, row.kpis_expected) == (2, 2)
    assert (row.period_start, row.period_end) == (Q3_FIRST_DAY, Q3_LAST_DAY) and row.finalized_at is None


@pytest.mark.asyncio
async def test_a_kpi_with_no_saved_result_is_left_out_and_every_department_still_gets_a_row(
    client, monkeypatch, db_session
):
    """One of two KPIs has a result: it stands alone (70.00), counted 1 of 2. Sales has no KPIs: an empty row."""
    w = await _world(client, monkeypatch, "ds2")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    await _save_kpi_result(db_session, w, lead_follow_up, "70")

    written = await _compute(db_session, w)

    dispatch = await _row(db_session, w.dispatch)
    sales = await _row(db_session, w.sales)
    assert written == 2  # both departments of the company got a row
    assert (dispatch.kpi_results_score, dispatch.kpis_counted, dispatch.kpis_expected) == (Decimal("70.00"), 1, 2)
    assert (sales.kpi_results_score, sales.kpis_counted, sales.kpis_expected) == (None, 0, 0)
    assert (sales.punctuality_score, sales.punctuality_on_time) == (None, 0)


@pytest.mark.asyncio
async def test_no_saved_results_means_no_data_not_zero(client, monkeypatch, db_session):
    """Two KPIs, nothing saved yet: the headline is empty with 0 of 2 counted, never 0%."""
    w = await _world(client, monkeypatch, "ds3")
    await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])

    await _compute(db_session, w)

    row = await _row(db_session, w.dispatch)
    assert row.kpi_results_score is None
    assert (row.kpis_counted, row.kpis_expected) == (0, 2)


@pytest.mark.asyncio
async def test_team_punctuality_counts_every_task_including_those_nobody_holds(client, monkeypatch, db_session):
    """One on time (Chidi's), one late (nobody holds it, no KPI), one never done: 1 / 1 / 1 = 50.00; a cancelled one is ignored."""
    w = await _world(client, monkeypatch, "ds4")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add_all(
        [
            _task(w, "on time", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))),
            _task(w, "late, nobody holds it, no KPI", None, None, **_done(at(8, 5), at(8, 9))),
            _task(w, "never done", lead_follow_up, w.bola.employee_id, due_at=at(9, 1)),
            _task(w, "cancelled", lead_follow_up, w.chidi.employee_id, status="cancelled", cancel_reason="x"),
        ]
    )
    await db_session.flush()

    await _compute(db_session, w)

    row = await _row(db_session, w.dispatch)
    assert (row.punctuality_on_time, row.punctuality_late, row.punctuality_not_done) == (1, 1, 1)
    assert row.punctuality_score == Decimal("50.00")
    # The two numbers are independent: punctuality is known even though no KPI result is saved yet.
    assert row.kpi_results_score is None


@pytest.mark.asyncio
async def test_tasks_of_one_department_do_not_count_for_another(client, monkeypatch, db_session):
    """A Sales task and a Dispatch task: each department only sees its own."""
    w = await _world(client, monkeypatch, "ds5")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add_all(
        [
            _task(w, "dispatch task", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))),
            _task(w, "sales task", None, None, department_id=uuid.UUID(w.sales), due_at=at(8, 1)),
        ]
    )
    await db_session.flush()

    await _compute(db_session, w)

    dispatch = await _row(db_session, w.dispatch)
    sales = await _row(db_session, w.sales)
    assert (dispatch.punctuality_on_time, dispatch.punctuality_not_done) == (1, 0)
    assert (sales.punctuality_on_time, sales.punctuality_not_done) == (0, 1)


@pytest.mark.asyncio
async def test_the_revenue_share_is_noted_and_kept_when_the_row_is_frozen(client, monkeypatch, db_session):
    """A running row follows a change of share; once frozen it keeps the share it had."""
    w = await _world(client, monkeypatch, "ds6")
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(
        update(Department).where(Department.id == uuid.UUID(w.dispatch)).values(is_critical=True, revenue_allocation_percentage=60)
    )
    service = ScoringService(db_session)
    await service.compute_department_scores(org_id, Q3_START, Q4_START, Q4_START)
    first = (await _row(db_session, w.dispatch)).revenue_allocation_percentage

    await db_session.execute(update(Department).where(Department.id == uuid.UUID(w.dispatch)).values(revenue_allocation_percentage=40))
    await service.compute_department_scores(org_id, Q3_START, Q4_START, Q4_START)
    running = (await _row(db_session, w.dispatch)).revenue_allocation_percentage
    await service.finalize_department_scores(org_id, Q3_START, Q4_START, Q4_START)
    await db_session.execute(update(Department).where(Department.id == uuid.UUID(w.dispatch)).values(revenue_allocation_percentage=25))
    written_after_freeze = await service.compute_department_scores(org_id, Q3_START, Q4_START, Q4_START)

    frozen = await _row(db_session, w.dispatch)
    assert (first, running) == (Decimal("60.00"), Decimal("40.00"))
    assert frozen.revenue_allocation_percentage == Decimal("40.00") and frozen.finalized_at is not None
    assert written_after_freeze == 0  # both departments were frozen: the job left them alone


@pytest.mark.asyncio
async def test_a_frozen_department_row_is_never_rewritten_when_results_or_tasks_change(
    client, monkeypatch, db_session
):
    """Close Q3, then save a new KPI result and change a task: the closed numbers do not move."""
    w = await _world(client, monkeypatch, "ds7")
    lead_follow_up, _ = await _two_kpis(client, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    done = _task(w, "on time", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30)))
    db_session.add(done)
    await db_session.flush()
    await _save_kpi_result(db_session, w, lead_follow_up, "70")
    service = ScoringService(db_session)

    frozen = await service.finalize_department_scores(org_id, Q3_START, Q4_START, now=Q4_START)
    before = await _row(db_session, w.dispatch)
    numbers = (before.kpi_results_score, before.punctuality_on_time, before.punctuality_late, before.finalized_at)
    await db_session.execute(update(Task).where(Task.id == done.id).values(completed_at=at(8, 20)))  # now it was late
    await db_session.execute(update(KPIScore).where(KPIScore.kpi_id == uuid.UUID(lead_follow_up)).values(score_percentage=Decimal("10")))
    again = await service.compute_department_scores(org_id, Q3_START, Q4_START, Q4_START)

    after = await _row(db_session, w.dispatch)
    assert frozen == 2 and again == 0  # both departments frozen, then left alone
    assert (after.kpi_results_score, after.punctuality_on_time, after.punctuality_late, after.finalized_at) == numbers
    assert after.kpi_results_score == Decimal("70.00") and after.punctuality_on_time == 1


@pytest.mark.asyncio
async def test_another_companys_departments_get_no_rows_here(client, monkeypatch, db_session):
    """Row-level security: computing for one company writes rows only for its own departments."""
    w = await _world(client, monkeypatch, "ds8")
    other = await _world(client, monkeypatch, "ds9")
    await set_org_context(db_session, w.owner["organization"]["id"])

    written = await _compute(db_session, w)

    rows = list((await db_session.execute(select(DepartmentScore))).scalars())
    assert written == 2 and len(rows) == 2
    assert {r.department_id for r in rows} == {uuid.UUID(w.dispatch), uuid.UUID(w.sales)}
    assert uuid.UUID(other.dispatch) not in {r.department_id for r in rows}
