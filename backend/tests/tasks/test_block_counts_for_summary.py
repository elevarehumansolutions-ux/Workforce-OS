"""Tests for TaskService.count_approved_blocks_by_category, the read helper for the executive summary (M12 slice G)."""
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.tasks.service import TaskService
from tests.conftest import set_org_context
from tests.tasks.test_task_blocks_table import _block
from tests.tasks.test_tasks_for_scoring import Q3_START, Q4_START, _task, at
from tests.tasks.test_tasks_router import _world


async def _count(db_session, w) -> dict:
    """The helper's answer for Q3 as {(department id, category): tasks}."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    rows = await TaskService(db_session).count_approved_blocks_by_category(Q3_START, Q4_START)
    return {(str(department_id), category): count for department_id, category, count in rows}


async def _held_back(db_session, w, task, **changes):
    """Record a block on the task (approved, in August, awaiting another department) with any field changed."""
    fields = {"review_status": "approved", "blocked_at": at(8, 10), "unblocked_at": at(8, 12)}
    fields.update(changes)
    if fields["review_status"] != "pending":
        # The database insists that a reviewed block says who reviewed it and when.
        fields["reviewed_by_user_id"] = uuid.UUID(w.owner["user"]["id"])
        fields["reviewed_at"] = at(8, 13)
    db_session.add(_block(w.owner["organization"]["id"], str(task.id), w.owner["user"]["id"], **fields))
    await db_session.flush()


@pytest.mark.asyncio
async def test_tasks_held_back_by_approved_blocks_are_counted_per_department_and_category(client, monkeypatch, db_session):
    """Two Dispatch tasks awaiting another department, one awaiting approval, one Sales task awaiting approval."""
    w = await _world(client, monkeypatch, "bc1")
    await set_org_context(db_session, w.owner["organization"]["id"])
    tasks = [_task(w, name) for name in ("a", "b", "c")] + [_task(w, "d", department_id=uuid.UUID(w.sales))]
    db_session.add_all(tasks)
    await db_session.flush()
    await _held_back(db_session, w, tasks[0])
    await _held_back(db_session, w, tasks[1])
    await _held_back(db_session, w, tasks[2], category="awaiting_approval")
    await _held_back(db_session, w, tasks[3], category="awaiting_approval")

    assert await _count(db_session, w) == {
        (w.dispatch, "awaiting_other_department"): 2,
        (w.dispatch, "awaiting_approval"): 1,
        (w.sales, "awaiting_approval"): 1,
    }


@pytest.mark.asyncio
async def test_one_task_blocked_twice_counts_once(client, monkeypatch, db_session):
    """It is tasks held back that are counted, not blocks."""
    w = await _world(client, monkeypatch, "bc2")
    await set_org_context(db_session, w.owner["organization"]["id"])
    task = _task(w, "twice")
    db_session.add(task)
    await db_session.flush()
    await _held_back(db_session, w, task)
    await _held_back(db_session, w, task, blocked_at=at(8, 20), unblocked_at=at(8, 22))

    assert await _count(db_session, w) == {(w.dispatch, "awaiting_other_department"): 1}


@pytest.mark.asyncio
async def test_only_approved_blocks_inside_the_period_on_live_tasks_count(client, monkeypatch, db_session):
    """Pending, rejected, out-of-period and deleted-task blocks are all left out."""
    w = await _world(client, monkeypatch, "bc3")
    await set_org_context(db_session, w.owner["organization"]["id"])
    tasks = [_task(w, name) for name in ("pending", "rejected", "before", "after", "deleted")]
    tasks[4].deleted_at = datetime.now(UTC)
    db_session.add_all(tasks)
    await db_session.flush()
    await _held_back(db_session, w, tasks[0], review_status="pending", unblocked_at=None)
    await _held_back(db_session, w, tasks[1], review_status="rejected")
    await _held_back(db_session, w, tasks[2], blocked_at=at(6, 30, 23), unblocked_at=at(7, 2))  # began before Q3
    await _held_back(db_session, w, tasks[3], blocked_at=datetime(2026, 10, 1, tzinfo=UTC), unblocked_at=at(10, 2))
    await _held_back(db_session, w, tasks[4])

    assert await _count(db_session, w) == {}
