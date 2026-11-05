"""Tests for working out and saving a person's score (M12 slice C)."""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.modules.scoring.models import EmployeeKPIScore
from app.modules.scoring.service import ScoringService
from app.modules.tasks.models import Task
from tests.conftest import set_org_context
from tests.tasks.test_task_blocks_table import _block
from tests.tasks.test_tasks_router import KPIS, _world

Q3_START = datetime(2026, 7, 1, tzinfo=UTC)
Q4_START = datetime(2026, 10, 1, tzinfo=UTC)  # also the first moment AFTER Q3
Q4_END = datetime(2027, 1, 1, tzinfo=UTC)
Q3_FIRST_DAY, Q3_LAST_DAY = date(2026, 7, 1), date(2026, 9, 30)
Q4_FIRST_DAY, Q4_LAST_DAY = date(2026, 10, 1), date(2026, 12, 31)
DAY = 86400


def at(month: int, day: int, hour: int = 12) -> datetime:
    """A moment in 2026, in UTC, noon by default."""
    return datetime(2026, month, day, hour, tzinfo=UTC)


async def _two_kpis(client, w) -> tuple[str, str]:
    """Lead Follow-up (weight 70) and Contract Paperwork (weight 30) for Dispatch."""
    ids = []
    for name, weight in (("Lead Follow-up", 70), ("Contract Paperwork", 30)):
        created = await client.post(
            KPIS, json={"department_id": w.dispatch, "name": name, "weight": weight}, headers=w.hr
        )
        assert created.status_code == 200
        ids.append(created.json()["id"])
    return ids[0], ids[1]


def _task(w, title: str, kpi_id, employee_id, **changes) -> Task:
    """A task in Dispatch, held by the given employee, linked to the KPI, with any field changed."""
    fields = {
        "organization_id": uuid.UUID(w.owner["organization"]["id"]),
        "department_id": uuid.UUID(w.dispatch),
        "title": title,
        "status": "open",
        "due_at": at(8, 1),
        "kpi_id": uuid.UUID(kpi_id) if kpi_id else None,
        "assigned_to_employee_id": uuid.UUID(employee_id) if employee_id else None,
    }
    fields.update(changes)
    return Task(**fields)


def _done(due, completed, **changes) -> dict:
    """The fields of a completed task."""
    return {"status": "completed", "due_at": due, "completed_at": completed, **changes}


async def _chidis_quarter(db_session, w, kpi_id) -> dict:
    """Chidi's seven Q3 tasks from the design example: 3 on time, 2 late, 1 never done, 1 cancelled."""
    chidi = w.chidi.employee_id
    tasks = {
        "A": _task(w, "A", kpi_id, chidi, **_done(at(7, 10), at(7, 8))),
        "B": _task(w, "B", kpi_id, chidi, **_done(at(7, 20), at(7, 20))),
        "C": _task(w, "C", kpi_id, chidi, **_done(at(8, 5), at(8, 9))),
        "D": _task(w, "D", kpi_id, chidi, **_done(at(8, 20), at(9, 25))),
        "E": _task(w, "E", kpi_id, chidi, due_at=at(9, 15)),
        "F": _task(w, "F", kpi_id, chidi, **_done(at(9, 1), at(9, 3), approved_blocked_seconds=3 * DAY)),
        "G": _task(w, "G", kpi_id, chidi, status="cancelled", cancel_reason="Client withdrew", due_at=at(9, 10)),
    }
    db_session.add_all(tasks.values())
    await db_session.flush()
    db_session.add(
        _block(
            w.owner["organization"]["id"], str(tasks["F"].id), w.owner["user"]["id"],
            blocked_at=at(8, 29), unblocked_at=at(9, 1),
            review_status="approved", reviewed_by_user_id=uuid.UUID(w.owner["user"]["id"]), reviewed_at=at(9, 2),
        )
    )
    await db_session.flush()
    return tasks


async def _rows(db_session, employee_id=None, period_start=Q3_FIRST_DAY) -> list[EmployeeKPIScore]:
    """The saved person-score rows of a period, optionally for one person."""
    stmt = select(EmployeeKPIScore).where(EmployeeKPIScore.period_start == period_start)
    if employee_id is not None:
        stmt = stmt.where(EmployeeKPIScore.employee_id == uuid.UUID(employee_id))
    # populate_existing: always show what the database holds NOW. Without it SQLAlchemy
    # would hand back the copy it loaded earlier, and a test could not see a rewrite.
    stmt = stmt.execution_options(populate_existing=True)
    return list((await db_session.execute(stmt)).scalars())


async def _compute_q3(db_session, w, now=Q4_START) -> int:
    """Work out Q3's person scores, the way the final write judges them (at the quarter's end)."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    return await ScoringService(db_session).compute_employee_scores(
        uuid.UUID(w.owner["organization"]["id"]), Q3_START, Q4_START, now
    )


@pytest.mark.asyncio
async def test_chidis_quarter_is_saved_as_three_on_time_two_late_one_not_done(client, monkeypatch, db_session):
    """One row for Chidi on Lead Follow-up: counts 3, 2, 1; score 66.67; the KPI's weight 70 noted."""
    w = await _world(client, monkeypatch, "es1")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    await _chidis_quarter(db_session, w, lead_follow_up)

    written = await _compute_q3(db_session, w)

    rows = await _rows(db_session)
    assert written == 1 and len(rows) == 1
    row = rows[0]
    assert row.employee_id == uuid.UUID(w.chidi.employee_id) and row.kpi_id == uuid.UUID(lead_follow_up)
    assert (row.tasks_on_time, row.tasks_late, row.tasks_not_done) == (3, 2, 1)
    assert row.score_percentage == Decimal("66.67") and row.weight_used == Decimal("70.00")
    assert (row.period_start, row.period_end) == (Q3_FIRST_DAY, Q3_LAST_DAY)
    assert row.finalized_at is None  # a running figure, not frozen


@pytest.mark.asyncio
async def test_running_the_job_again_refreshes_the_same_row(client, monkeypatch, db_session):
    """No duplicates: a second run updates the row, and a changed task changes the numbers."""
    w = await _world(client, monkeypatch, "es2")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    tasks = await _chidis_quarter(db_session, w, lead_follow_up)
    await _compute_q3(db_session, w)

    # Task E (never done) is finally completed, late, but inside the quarter.
    await db_session.execute(
        update(Task).where(Task.id == tasks["E"].id).values(status="completed", completed_at=at(9, 20))
    )
    await _compute_q3(db_session, w, now=at(9, 25))

    rows = await _rows(db_session)
    assert len(rows) == 1
    assert (rows[0].tasks_on_time, rows[0].tasks_late, rows[0].tasks_not_done) == (3, 3, 0)
    assert rows[0].score_percentage == Decimal("75.00")


@pytest.mark.asyncio
async def test_a_frozen_period_is_never_rewritten_even_when_the_tasks_change(client, monkeypatch, db_session):
    """Close Q3, then change a task and run the job again: the closed row keeps its numbers and its weight."""
    w = await _world(client, monkeypatch, "es3")
    lead_follow_up, _ = await _two_kpis(client, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    tasks = await _chidis_quarter(db_session, w, lead_follow_up)
    service = ScoringService(db_session)

    frozen = await service.finalize_employee_scores(org_id, Q3_START, Q4_START, now=Q4_START)
    before = (await _rows(db_session))[0]
    final_numbers = (before.tasks_on_time, before.tasks_late, before.tasks_not_done, before.weight_used)
    await db_session.execute(update(Task).where(Task.id == tasks["E"].id).values(status="cancelled", cancel_reason="x"))
    await db_session.execute(update(Task).where(Task.title == "A").values(due_at=at(7, 5)))  # now it was late
    written_again = await service.compute_employee_scores(org_id, Q3_START, Q4_START, Q4_START)

    after = (await _rows(db_session))[0]
    assert frozen == 1 and before.finalized_at is not None
    assert written_again == 0  # the job found a frozen row and left it alone
    assert (after.tasks_on_time, after.tasks_late, after.tasks_not_done, after.weight_used) == final_numbers
    assert after.finalized_at == before.finalized_at


@pytest.mark.asyncio
async def test_the_final_write_judges_at_the_end_of_the_quarter(client, monkeypatch, db_session):
    """Due 20 Sept and finished on 5 Oct: Q3's final card says not done, although the job runs on 6 Oct."""
    w = await _world(client, monkeypatch, "es4")
    lead_follow_up, _ = await _two_kpis(client, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add(_task(w, "late finisher", lead_follow_up, w.chidi.employee_id, **_done(at(9, 20), at(10, 5))))
    await db_session.flush()

    await ScoringService(db_session).finalize_employee_scores(org_id, Q3_START, Q4_START, now=at(10, 6))

    row = (await _rows(db_session))[0]
    assert (row.tasks_on_time, row.tasks_late, row.tasks_not_done) == (0, 0, 1)
    assert row.score_percentage == Decimal("0.00")  # a real zero, not "no data"


@pytest.mark.asyncio
async def test_a_row_whose_tasks_have_gone_is_reset_to_no_data(client, monkeypatch, db_session):
    """Cancel every task after the first run: the running row becomes zero counts and an empty score."""
    w = await _world(client, monkeypatch, "es5")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add(_task(w, "only one", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))))
    await db_session.flush()
    await _compute_q3(db_session, w)
    assert (await _rows(db_session))[0].score_percentage == Decimal("100.00")

    await db_session.execute(update(Task).where(Task.title == "only one").values(status="cancelled", completed_at=None, cancel_reason="x"))
    await _compute_q3(db_session, w)

    row = (await _rows(db_session))[0]
    assert (row.tasks_on_time, row.tasks_late, row.tasks_not_done) == (0, 0, 0)
    assert row.score_percentage is None


@pytest.mark.asyncio
async def test_tasks_that_do_not_belong_on_a_persons_card_are_ignored(client, monkeypatch, db_session):
    """Nobody holds it, no KPI link, no deadline, cancelled, outside the quarter: none of these makes a row."""
    w = await _world(client, monkeypatch, "es6")
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    chidi = w.chidi.employee_id
    db_session.add_all(
        [
            _task(w, "nobody holds it", lead_follow_up, None, **_done(at(8, 1), at(7, 30))),
            _task(w, "no KPI", None, chidi, **_done(at(8, 1), at(7, 30))),
            _task(w, "no deadline", lead_follow_up, chidi, due_at=None),
            _task(w, "cancelled", lead_follow_up, chidi, status="cancelled", cancel_reason="x"),
            _task(w, "next quarter", lead_follow_up, chidi, **_done(at(11, 1), at(10, 20))),
        ]
    )
    await db_session.flush()

    written = await _compute_q3(db_session, w)

    assert written == 0 and await _rows(db_session) == []


@pytest.mark.asyncio
async def test_the_kpi_weight_is_noted_when_written_and_kept_when_frozen(client, monkeypatch, db_session):
    """A running row follows a weight change; a frozen row keeps the weight it had."""
    w = await _world(client, monkeypatch, "es7")
    lead_follow_up, _ = await _two_kpis(client, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add(_task(w, "one", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))))
    await db_session.flush()
    service = ScoringService(db_session)
    await service.compute_employee_scores(org_id, Q3_START, Q4_START, Q4_START)
    patch = await client.patch(f"{KPIS}/{lead_follow_up}", json={"weight": 50}, headers=w.hr)
    assert patch.status_code == 200
    await set_org_context(db_session, w.owner["organization"]["id"])

    await service.compute_employee_scores(org_id, Q3_START, Q4_START, Q4_START)
    refreshed_weight = (await _rows(db_session))[0].weight_used
    await service.finalize_employee_scores(org_id, Q3_START, Q4_START, Q4_START)
    await client.patch(f"{KPIS}/{lead_follow_up}", json={"weight": 40}, headers=w.hr)
    await set_org_context(db_session, w.owner["organization"]["id"])
    await service.compute_employee_scores(org_id, Q3_START, Q4_START, Q4_START)

    assert refreshed_weight == Decimal("50.00")
    assert (await _rows(db_session))[0].weight_used == Decimal("50.00")  # frozen at 50, not the new 40


@pytest.mark.asyncio
async def test_a_task_held_back_in_q3_is_marked_in_q4_and_q3_stays_as_published(client, monkeypatch, db_session):
    """Due 25 Sept with a block pending at close: out of Q3's final card; once rejected it is NOT DONE on Q4's."""
    w = await _world(client, monkeypatch, "es8")
    lead_follow_up, _ = await _two_kpis(client, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, w.owner["organization"]["id"])
    held = _task(w, "held back", lead_follow_up, w.chidi.employee_id, due_at=at(9, 25))
    steady = _task(w, "steady", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30)))
    db_session.add_all([held, steady])
    await db_session.flush()
    block = _block(
        w.owner["organization"]["id"], str(held.id), w.owner["user"]["id"],
        blocked_at=at(9, 24), unblocked_at=at(9, 26),
    )
    db_session.add(block)
    await db_session.flush()
    service = ScoringService(db_session)

    await service.finalize_employee_scores(org_id, Q3_START, Q4_START, now=Q4_START)  # the block is still pending
    q3_after_close = (await _rows(db_session))[0]
    reviewer = uuid.UUID(w.owner["user"]["id"])
    await db_session.execute(
        update(type(block))
        .where(type(block).id == block.id)
        .values(review_status="rejected", reviewed_by_user_id=reviewer, reviewed_at=at(10, 10))
    )
    await service.finalize_employee_scores(org_id, Q3_START, Q4_START, now=at(10, 11))  # Q3 is run once more
    await service.finalize_employee_scores(org_id, Q4_START, Q4_END, now=Q4_END)

    q3 = (await _rows(db_session, period_start=Q3_FIRST_DAY))[0]
    q4 = (await _rows(db_session, period_start=Q4_FIRST_DAY))[0]
    assert (q3_after_close.tasks_on_time, q3_after_close.tasks_not_done) == (1, 0)  # "held back" was not on it
    assert (q3.tasks_on_time, q3.tasks_late, q3.tasks_not_done) == (1, 0, 0)       # and still is not
    assert q3.finalized_at == q3_after_close.finalized_at                           # Q3 was never rewritten
    assert (q4.tasks_on_time, q4.tasks_late, q4.tasks_not_done) == (0, 0, 1)       # it is marked in Q4
    assert q4.score_percentage == Decimal("0.00")


@pytest.mark.asyncio
async def test_each_person_and_kpi_has_their_own_row_and_other_companies_are_invisible(
    client, monkeypatch, db_session
):
    """Chidi and Bola on two KPIs make separate rows; another company's tasks never leak in."""
    w = await _world(client, monkeypatch, "es9")
    other = await _world(client, monkeypatch, "es10")
    lead_follow_up, paperwork = await _two_kpis(client, w)
    other_kpi, _ = await _two_kpis(client, other)
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add_all(
        [
            _task(w, "c1", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))),
            _task(w, "c2", paperwork, w.chidi.employee_id, **_done(at(8, 1), at(8, 5))),
            _task(w, "b1", lead_follow_up, w.bola.employee_id, due_at=at(8, 1)),
        ]
    )
    await db_session.flush()
    await set_org_context(db_session, other.owner["organization"]["id"])
    db_session.add(_task(other, "theirs", other_kpi, other.chidi.employee_id, **_done(at(8, 1), at(7, 30))))
    await db_session.flush()

    written = await _compute_q3(db_session, w)

    rows = {(r.employee_id, r.kpi_id): r for r in await _rows(db_session)}
    chidi, bola = uuid.UUID(w.chidi.employee_id), uuid.UUID(w.bola.employee_id)
    assert written == 3 and len(rows) == 3
    assert rows[(chidi, uuid.UUID(lead_follow_up))].score_percentage == Decimal("100.00")
    assert rows[(chidi, uuid.UUID(paperwork))].score_percentage == Decimal("50.00")
    assert rows[(bola, uuid.UUID(lead_follow_up))].score_percentage == Decimal("0.00")
    assert rows[(chidi, uuid.UUID(paperwork))].weight_used == Decimal("30.00")
