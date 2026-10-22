"""Tests for TaskService.list_tasks_for_scoring, the read helper for the Scoring module (M12 slice C)."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.tasks.models import Task
from app.modules.tasks.service import TaskService
from tests.conftest import set_org_context
from tests.tasks.test_task_blocks_table import _block
from tests.tasks.test_tasks_router import _world

Q3_START = datetime(2026, 7, 1, tzinfo=UTC)
Q4_START = datetime(2026, 10, 1, tzinfo=UTC)
Q4_END = datetime(2027, 1, 1, tzinfo=UTC)
DAY = 86400


def at(month: int, day: int, hour: int = 12) -> datetime:
    """A moment in 2026, in UTC, noon by default."""
    return datetime(2026, month, day, hour, tzinfo=UTC)


def _task(world, title: str, **changes) -> Task:
    """A task row in Dispatch with a Q3 deadline, with any field changed for the case at hand."""
    fields = {
        "organization_id": uuid.UUID(world.owner["organization"]["id"]),
        "department_id": uuid.UUID(world.dispatch),
        "title": title,
        "status": "open",
        "due_at": at(8, 1),
    }
    fields.update(changes)
    return Task(**fields)


async def _titles(db_session, world, start, end) -> dict:
    """Ask the helper for a period and return its rows keyed by task title."""
    await set_org_context(db_session, world.owner["organization"]["id"])
    rows = await TaskService(db_session).list_tasks_for_scoring(start, end)
    # The helper returns ids, not titles, so look the titles up for readable assertions.
    result = await db_session.execute(select(Task.id, Task.title))
    titles = {task_id: title for task_id, title in result.all()}
    return {titles[row.task_id]: row for row in rows}


async def _block_for(db_session, world, task: Task, **changes) -> None:
    """Add a closed block to a task (reviewed or pending, as the changes say)."""
    org_id = world.owner["organization"]["id"]
    fields = {"blocked_at": at(8, 1) - timedelta(days=2), "unblocked_at": at(8, 1) - timedelta(days=1)}
    fields.update(changes)
    db_session.add(_block(org_id, str(task.id), world.owner["user"]["id"], **fields))
    await db_session.flush()


@pytest.mark.asyncio
async def test_only_tasks_that_could_count_in_the_period_come_back(client, monkeypatch, db_session):
    """Inside the period, yes; before it, after it, cancelled, or with no deadline, no."""
    w = await _world(client, monkeypatch, "ts1")
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add_all(
        [
            _task(w, "inside", due_at=at(8, 15)),
            _task(w, "first moment", due_at=Q3_START),
            _task(w, "before the period", due_at=Q3_START - timedelta(seconds=1)),
            _task(w, "exactly at the end", due_at=Q4_START),
            _task(w, "after the period", due_at=at(11, 1)),
            _task(w, "cancelled", status="cancelled", cancel_reason="Not needed", due_at=at(8, 15)),
            _task(w, "no deadline", due_at=None),
        ]
    )
    await db_session.flush()

    q3 = await _titles(db_session, w, Q3_START, Q4_START)

    assert set(q3) == {"inside", "first moment"}


@pytest.mark.asyncio
async def test_approved_blocked_time_moves_a_task_to_the_period_of_its_real_deadline(
    client, monkeypatch, db_session
):
    """Due 29 Sept with 5 approved days is really due 4 Oct: it is a Q4 candidate, not a Q3 one."""
    w = await _world(client, monkeypatch, "ts2")
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add(_task(w, "pushed into Q4", due_at=at(9, 29), approved_blocked_seconds=5 * DAY))
    await db_session.flush()

    q3 = await _titles(db_session, w, Q3_START, Q4_START)
    q4 = await _titles(db_session, w, Q4_START, Q4_END)

    assert "pushed into Q4" not in q3
    assert "pushed into Q4" in q4


@pytest.mark.asyncio
async def test_a_block_reviewed_after_the_period_makes_the_task_a_candidate_for_the_next_one(
    client, monkeypatch, db_session
):
    """Due 25 Sept, reviewed 10 Oct: returned for Q3 (its deadline) and for Q4 (where it will be marked)."""
    w = await _world(client, monkeypatch, "ts3")
    await set_org_context(db_session, w.owner["organization"]["id"])
    carried = _task(w, "carried over", due_at=at(9, 25))
    db_session.add(carried)
    await db_session.flush()
    await _block_for(
        db_session, w, carried,
        review_status="rejected", reviewed_by_user_id=uuid.UUID(w.owner["user"]["id"]), reviewed_at=at(10, 10),
    )

    q3 = await _titles(db_session, w, Q3_START, Q4_START)
    q4 = await _titles(db_session, w, Q4_START, Q4_END)

    assert q3["carried over"].last_block_reviewed_at == at(10, 10)
    assert q4["carried over"].last_block_reviewed_at == at(10, 10)


@pytest.mark.asyncio
async def test_the_block_facts_are_right_for_none_pending_approved_and_a_mix(client, monkeypatch, db_session):
    """No block: not pending, never reviewed. A pending one: pending. Approved only: not pending, reviewed. Mixed: pending."""
    w = await _world(client, monkeypatch, "ts4")
    await set_org_context(db_session, w.owner["organization"]["id"])
    reviewer = uuid.UUID(w.owner["user"]["id"])
    plain = _task(w, "plain")
    waiting = _task(w, "waiting")
    reviewed = _task(w, "reviewed")
    mixed = _task(w, "mixed")
    db_session.add_all([plain, waiting, reviewed, mixed])
    await db_session.flush()
    await _block_for(db_session, w, waiting)  # still pending
    await _block_for(
        db_session, w, reviewed, review_status="approved", reviewed_by_user_id=reviewer, reviewed_at=at(7, 31)
    )
    await _block_for(
        db_session, w, mixed, review_status="approved", reviewed_by_user_id=reviewer, reviewed_at=at(7, 30)
    )
    await _block_for(
        db_session, w, mixed, blocked_at=at(7, 29), unblocked_at=at(7, 29, 18)
    )  # a second block, still pending

    rows = await _titles(db_session, w, Q3_START, Q4_START)

    assert (rows["plain"].has_pending_block, rows["plain"].last_block_reviewed_at) == (False, None)
    assert (rows["waiting"].has_pending_block, rows["waiting"].last_block_reviewed_at) == (True, None)
    assert (rows["reviewed"].has_pending_block, rows["reviewed"].last_block_reviewed_at) == (False, at(7, 31))
    assert (rows["mixed"].has_pending_block, rows["mixed"].last_block_reviewed_at) == (True, at(7, 30))


@pytest.mark.asyncio
async def test_each_row_carries_the_tasks_own_facts_and_other_organizations_are_invisible(
    client, monkeypatch, db_session
):
    """Department, KPI, assignee, status and times round-trip; another company's tasks never appear."""
    w = await _world(client, monkeypatch, "ts5")
    other = await _world(client, monkeypatch, "ts6")
    await set_org_context(db_session, w.owner["organization"]["id"])
    done = _task(
        w, "done", status="completed", completed_at=at(7, 30), due_at=at(8, 1),
        assigned_to_employee_id=uuid.UUID(w.chidi.employee_id), approved_blocked_seconds=DAY,
    )
    db_session.add(done)
    await db_session.flush()
    await set_org_context(db_session, other.owner["organization"]["id"])
    db_session.add(_task(other, "someone else's", due_at=at(8, 15)))
    await db_session.flush()

    await set_org_context(db_session, w.owner["organization"]["id"])
    rows = await TaskService(db_session).list_tasks_for_scoring(Q3_START, Q4_START)

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == done.id and row.status == "completed"
    assert (row.department_id, row.kpi_id) == (uuid.UUID(w.dispatch), None)
    assert row.assigned_to_employee_id == uuid.UUID(w.chidi.employee_id)
    assert (row.due_at, row.completed_at, row.approved_blocked_seconds) == (at(8, 1), at(7, 30), DAY)


@pytest.mark.asyncio
async def test_completed_tasks_of_a_kpi_are_counted_inside_the_period_only(client, monkeypatch, db_session):
    """Start included, end excluded; open, cancelled and other-KPI tasks do not count."""
    w = await _world(client, monkeypatch, "ts7")
    mine = (await client.post(
        "/api/v1/kpis", json={"department_id": w.dispatch, "name": "Deals closed", "weight": 60}, headers=w.hr
    )).json()["id"]
    other = (await client.post(
        "/api/v1/kpis", json={"department_id": w.dispatch, "name": "Calls made", "weight": 40}, headers=w.hr
    )).json()["id"]
    await set_org_context(db_session, w.owner["organization"]["id"])

    def done(title, when, kpi=mine, **changes):
        return _task(w, title, kpi_id=uuid.UUID(kpi), status="completed", completed_at=when, **changes)

    db_session.add_all(
        [
            done("inside", at(8, 15)),
            done("first moment", Q3_START),
            done("last second", Q4_START - timedelta(seconds=1)),
            done("exactly at the end", Q4_START),
            done("before", Q3_START - timedelta(seconds=1)),
            done("other KPI", at(8, 15), kpi=other),
            _task(w, "still open", kpi_id=uuid.UUID(mine)),
            _task(w, "cancelled", kpi_id=uuid.UUID(mine), status="cancelled", cancel_reason="x"),
        ]
    )
    await db_session.flush()
    service = TaskService(db_session)

    q3 = await service.count_completed_tasks_for_kpi(uuid.UUID(mine), Q3_START, Q4_START)
    q4 = await service.count_completed_tasks_for_kpi(uuid.UUID(mine), Q4_START, Q4_END)
    nobody = await service.count_completed_tasks_for_kpi(uuid.uuid4(), Q3_START, Q4_START)

    assert (q3, q4, nobody) == (3, 1, 0)
