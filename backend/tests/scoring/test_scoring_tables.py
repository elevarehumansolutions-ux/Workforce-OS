"""Tests for the scoring tables' own rules (M12 slice A).

These insert rows directly, so they prove the DATABASE refuses bad data
whatever the application code does.
"""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.modules.scoring.models import DepartmentScore, EmployeeKPIScore, ExecutiveSummary
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import KPIS, _world
from tests.workflow.test_workflow_tables import _refused

Q3_START, Q3_END = date(2026, 7, 1), date(2026, 9, 30)
Q4_START, Q4_END = date(2026, 10, 1), date(2026, 12, 31)


async def _kpi_id(client, w) -> str:
    """Create a KPI for the Dispatch department and return its id."""
    created = await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 100}, headers=w.hr
    )
    assert created.status_code == 200
    return created.json()["id"]


def _employee_score(org_id, employee_id, kpi_id, **changes) -> EmployeeKPIScore:
    """A valid person-score row (Chidi's Q3: 3 on time, 2 late, 1 not done = 66.67), with any field changed."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "employee_id": uuid.UUID(employee_id),
        "kpi_id": uuid.UUID(kpi_id),
        "period_start": Q3_START,
        "period_end": Q3_END,
        "tasks_on_time": 3,
        "tasks_late": 2,
        "tasks_not_done": 1,
        "score_percentage": Decimal("66.67"),
        "weight_used": Decimal("70.00"),
    }
    fields.update(changes)
    return EmployeeKPIScore(**fields)


@pytest.mark.asyncio
async def test_the_database_enforces_the_rules_of_a_persons_score(client, monkeypatch, db_session):
    """One row per person, KPI and period; no negative counts; a score of 0 to 100; "no data" is empty, never 0."""
    w = await _world(client, monkeypatch, "sc1")
    org_id = w.owner["organization"]["id"]
    kpi_id = await _kpi_id(client, w)
    await set_org_context(db_session, org_id)
    chidi = w.chidi.employee_id

    first = _employee_score(org_id, chidi, kpi_id)
    assert not await _refused(db_session, first)
    # The same person, KPI and period a second time.
    assert await _refused(db_session, _employee_score(org_id, chidi, kpi_id))
    # The same person and KPI in the next period is fine.
    assert not await _refused(
        db_session, _employee_score(org_id, chidi, kpi_id, period_start=Q4_START, period_end=Q4_END)
    )
    # Someone with no valid tasks: no data is empty, and that is allowed.
    assert not await _refused(
        db_session,
        _employee_score(
            org_id, w.bola.employee_id, kpi_id,
            tasks_on_time=0, tasks_late=0, tasks_not_done=0, score_percentage=None,
        ),
    )
    # A negative count.
    assert await _refused(
        db_session, _employee_score(org_id, w.tunde.employee_id, kpi_id, tasks_late=-1)
    )
    # A score above 100, and one below 0.
    assert await _refused(
        db_session, _employee_score(org_id, w.dana.employee_id, kpi_id, score_percentage=Decimal("100.01"))
    )
    assert await _refused(
        db_session, _employee_score(org_id, w.sam.employee_id, kpi_id, score_percentage=Decimal("-1"))
    )
    # The period ends before it starts.
    assert await _refused(
        db_session,
        _employee_score(org_id, w.tunde.employee_id, kpi_id, period_start=Q3_END, period_end=Q3_START),
    )
    # A weight outside 0 to 100.
    assert await _refused(
        db_session, _employee_score(org_id, w.tunde.employee_id, kpi_id, weight_used=Decimal("100.01"))
    )


@pytest.mark.asyncio
async def test_no_data_can_never_be_stored_as_zero_or_a_score_without_tasks(client, monkeypatch, db_session):
    """Score present with no tasks, and score empty while tasks exist, are both refused."""
    w = await _world(client, monkeypatch, "sc2")
    org_id = w.owner["organization"]["id"]
    kpi_id = await _kpi_id(client, w)
    await set_org_context(db_session, org_id)

    score_with_no_tasks = _employee_score(
        org_id, w.chidi.employee_id, kpi_id,
        tasks_on_time=0, tasks_late=0, tasks_not_done=0, score_percentage=Decimal("0"),
    )
    no_score_but_tasks = _employee_score(org_id, w.bola.employee_id, kpi_id, score_percentage=None)

    assert await _refused(db_session, score_with_no_tasks)
    assert await _refused(db_session, no_score_but_tasks)


def _period(n: int) -> dict:
    """A distinct one-month period per case, so only the rule under test can refuse a row."""
    return {"period_start": date(2025, n, 1), "period_end": date(2025, n, 28)}


def _department_score(org_id, department_id, **changes) -> DepartmentScore:
    """A valid department row (Sales, Q3: results 70 from 1 of 1 KPI, punctuality 92.86, revenue share 60)."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "department_id": uuid.UUID(department_id),
        "period_start": Q3_START,
        "period_end": Q3_END,
        "kpi_results_score": Decimal("70.00"),
        "kpis_counted": 1,
        "kpis_expected": 1,
        "punctuality_on_time": 6,
        "punctuality_late": 1,
        "punctuality_not_done": 0,
        "punctuality_score": Decimal("92.86"),
        "revenue_allocation_percentage": Decimal("60.00"),
    }
    fields.update(changes)
    return DepartmentScore(**fields)


@pytest.mark.asyncio
async def test_the_database_enforces_the_rules_of_a_department_score(client, monkeypatch, db_session):
    """One row per department and period; results may exceed 100; "no data" is empty; N never exceeds M."""
    w = await _world(client, monkeypatch, "sc3")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    sales = w.sales

    assert not await _refused(db_session, _department_score(org_id, sales))
    # The same department and period again.
    assert await _refused(db_session, _department_score(org_id, sales))
    # The same department in the next period, and another department in the same one, are fine.
    assert not await _refused(
        db_session, _department_score(org_id, sales, period_start=Q4_START, period_end=Q4_END)
    )
    assert not await _refused(db_session, _department_score(org_id, w.dispatch))
    # A team that beat its target: results above 100 are allowed.
    assert not await _refused(
        db_session, _department_score(org_id, sales, **_period(1), kpi_results_score=Decimal("112.50"))
    )
    # A department with no KPI result and no tasks yet: both numbers empty, and no revenue share set.
    assert not await _refused(
        db_session,
        _department_score(
            org_id, sales, **_period(2),
            kpi_results_score=None, kpis_counted=0, kpis_expected=2,
            punctuality_on_time=0, punctuality_late=0, punctuality_not_done=0, punctuality_score=None,
            revenue_allocation_percentage=None,
        ),
    )
    # Results below zero.
    assert await _refused(
        db_session, _department_score(org_id, sales, **_period(3), kpi_results_score=Decimal("-0.01"))
    )
    # More KPIs counted than the department has.
    assert await _refused(db_session, _department_score(org_id, sales, **_period(4), kpis_counted=2, kpis_expected=1))
    # A negative count.
    assert await _refused(db_session, _department_score(org_id, sales, **_period(5), punctuality_late=-1))
    # Punctuality above 100, and a revenue share above 100.
    assert await _refused(
        db_session, _department_score(org_id, sales, **_period(6), punctuality_score=Decimal("100.01"))
    )
    assert await _refused(
        db_session, _department_score(org_id, sales, **_period(7), revenue_allocation_percentage=Decimal("100.01"))
    )
    # The period ends before it starts.
    assert await _refused(
        db_session, _department_score(org_id, sales, period_start=Q3_END, period_end=Q3_START)
    )


@pytest.mark.asyncio
async def test_a_department_never_stores_no_data_as_a_number(client, monkeypatch, db_session):
    """A results score with no KPI counted, and a punctuality score with no tasks, are refused (and the reverse)."""
    w = await _world(client, monkeypatch, "sc4")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    results_with_no_kpi = _department_score(org_id, w.sales, **_period(1), kpis_counted=0, kpis_expected=1)
    no_results_but_a_kpi = _department_score(org_id, w.sales, **_period(2), kpi_results_score=None)
    punctuality_with_no_tasks = _department_score(
        org_id, w.sales, **_period(3), punctuality_on_time=0, punctuality_late=0, punctuality_not_done=0
    )
    no_punctuality_but_tasks = _department_score(org_id, w.sales, **_period(4), punctuality_score=None)

    assert await _refused(db_session, results_with_no_kpi)
    assert await _refused(db_session, no_results_but_a_kpi)
    assert await _refused(db_session, punctuality_with_no_tasks)
    assert await _refused(db_session, no_punctuality_but_tasks)


def _summary(org_id, **changes) -> ExecutiveSummary:
    """A valid summary row for Q3, with any field changed for the case at hand."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "period_start": Q3_START,
        "period_end": Q3_END,
        "summary_text": "Sales missed its target by 30% while the team stayed punctual at 86%.",
        "facts_fingerprint": "a" * 64,
    }
    fields.update(changes)
    return ExecutiveSummary(**fields)


@pytest.mark.asyncio
async def test_the_database_enforces_the_rules_of_an_executive_summary(client, monkeypatch, db_session):
    """One summary per company and period; the text is not blank; the source is ai or plain; it can be frozen."""
    w = await _world(client, monkeypatch, "sc5")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    first = _summary(org_id)
    assert not await _refused(db_session, first)
    assert first.source == "ai"  # the default when nothing says otherwise
    # A second summary for the same company and period (the weekly job must update the row instead).
    assert await _refused(db_session, _summary(org_id))
    # The next period is fine, and so is the plain fact-only fallback, and a frozen summary.
    assert not await _refused(db_session, _summary(org_id, period_start=Q4_START, period_end=Q4_END))
    assert not await _refused(db_session, _summary(org_id, **_period(1), source="plain"))
    assert not await _refused(db_session, _summary(org_id, **_period(2), finalized_at=datetime.now(UTC)))
    # A source that is neither.
    assert await _refused(db_session, _summary(org_id, **_period(3), source="robot"))
    # Blank text, and text that is only spaces.
    assert await _refused(db_session, _summary(org_id, **_period(4), summary_text=""))
    assert await _refused(db_session, _summary(org_id, **_period(5), summary_text="   "))
    # No fingerprint of the facts.
    assert await _refused(db_session, _summary(org_id, **_period(6), facts_fingerprint=None))
    # The period ends before it starts.
    assert await _refused(db_session, _summary(org_id, period_start=Q3_END, period_end=Q3_START))


@pytest.mark.asyncio
async def test_another_organization_cannot_see_any_scoring_row(client, monkeypatch, db_session):
    """Row-level security covers all three new tables."""
    w = await _world(client, monkeypatch, "sc6")
    org_id = w.owner["organization"]["id"]
    kpi_id = await _kpi_id(client, w)
    await set_org_context(db_session, org_id)
    db_session.add_all(
        [
            _employee_score(org_id, w.chidi.employee_id, kpi_id),
            _department_score(org_id, w.sales),
            _summary(org_id),
        ]
    )
    await db_session.flush()

    async def count_rows() -> tuple[int, int, int]:
        counts = []
        for model in (EmployeeKPIScore, DepartmentScore, ExecutiveSummary):
            result = await db_session.execute(select(func.count()).select_from(model))
            counts.append(result.scalar_one())
        return tuple(counts)

    mine = await count_rows()
    await set_org_context(db_session, uuid.uuid4())
    someone_elses = await count_rows()

    assert (mine, someone_elses) == ((1, 1, 1), (0, 0, 0))


async def _statement_refused(db_session, statement) -> bool:
    """Whether the database refuses to run ``statement`` (an UPDATE or a DELETE)."""
    try:
        async with db_session.begin_nested():  # a savepoint, so one refusal doesn't spoil the test
            await db_session.execute(statement)
    except IntegrityError:
        return True
    return False


async def _check_the_lock(db_session, model, row, allowed_change: dict) -> None:
    """Walk one table through its life: running (changes allowed), frozen once, then locked for good."""
    db_session.add(row)
    await db_session.flush()
    this_row = model.id == row.id

    # While the period is open, the row is a running figure: it can be changed.
    assert not await _statement_refused(db_session, update(model).where(this_row).values(**allowed_change))
    # Freezing it (filling finalized_at for the first time) is allowed.
    assert not await _statement_refused(
        db_session, update(model).where(this_row).values(finalized_at=datetime.now(UTC))
    )
    # Frozen: no change, no un-freezing, no delete.
    assert await _statement_refused(db_session, update(model).where(this_row).values(**allowed_change))
    assert await _statement_refused(db_session, update(model).where(this_row).values(finalized_at=None))
    assert await _statement_refused(db_session, delete(model).where(this_row))
    # And the row is still there.
    still_there = await db_session.execute(select(func.count()).select_from(model).where(this_row))
    assert still_there.scalar_one() == 1


@pytest.mark.asyncio
async def test_a_frozen_row_can_no_longer_be_changed_or_deleted(client, monkeypatch, db_session):
    """The lock on a closed period, for a person's score, a department's score and a summary."""
    w = await _world(client, monkeypatch, "sc7")
    org_id = w.owner["organization"]["id"]
    kpi_id = await _kpi_id(client, w)
    await set_org_context(db_session, org_id)

    await _check_the_lock(
        db_session, EmployeeKPIScore, _employee_score(org_id, w.chidi.employee_id, kpi_id), {"tasks_late": 3}
    )
    await _check_the_lock(
        db_session, DepartmentScore, _department_score(org_id, w.sales), {"punctuality_late": 2}
    )
    await _check_the_lock(
        db_session, ExecutiveSummary, _summary(org_id), {"summary_text": "A rewritten summary."}
    )


@pytest.mark.asyncio
async def test_a_row_that_was_never_frozen_can_still_be_deleted(client, monkeypatch, db_session):
    """The lock only protects closed periods: a running row can still be removed."""
    w = await _world(client, monkeypatch, "sc8")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    running = _summary(org_id)
    db_session.add(running)
    await db_session.flush()

    refused = await _statement_refused(db_session, delete(ExecutiveSummary).where(ExecutiveSummary.id == running.id))

    assert refused is False
