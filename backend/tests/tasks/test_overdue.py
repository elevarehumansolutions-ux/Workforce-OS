"""Tests for the overdue rule (M10 slices C and E).

``test_is_overdue`` checks the Python form on its own. The agreement tests below
check that the flag (Python) and the ``?overdue=`` filter (SQL) pick the same
tasks, so the two forms can't drift apart.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.tasks.enums import TaskStatus
from app.modules.tasks.models import Task
from app.modules.tasks.overdue import is_overdue
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import TASKS, _ids, _world
from tests.tasks.test_tasks_router import _task as _create_task_via_api

LONG_AGO = "2020-01-01T00:00:00+00:00"
FAR_AHEAD = "2099-01-01T00:00:00+00:00"

NOW = datetime(2026, 10, 8, 17, 0, 0, tzinfo=UTC)


def _task(status: TaskStatus, due_at: datetime | None, blocked=False, approved_seconds=0) -> Task:
    """A task held in memory, as the database would give it back."""
    return Task(
        status=status.value,
        due_at=due_at,
        blocked_since=NOW - timedelta(hours=1) if blocked else None,
        approved_blocked_seconds=approved_seconds,
    )


@pytest.mark.parametrize(
    "status, due_at, blocked, approved_seconds, expected",
    [
        (TaskStatus.OPEN, NOW - timedelta(seconds=1), False, 0, True),            # one second late
        (TaskStatus.IN_PROGRESS, NOW - timedelta(days=3), False, 0, True),
        (TaskStatus.OPEN, NOW, False, 0, False),                                  # exactly at the deadline: not yet
        (TaskStatus.OPEN, NOW + timedelta(seconds=1), False, 0, False),
        (TaskStatus.OPEN, None, False, 0, False),                                 # no deadline is never overdue
        (TaskStatus.COMPLETED, NOW - timedelta(days=3), False, 0, False),         # finished work isn't overdue
        (TaskStatus.CANCELLED, NOW - timedelta(days=3), False, 0, False),         # cancelled is neither done nor late
        # Blocked time (slice E):
        (TaskStatus.OPEN, NOW - timedelta(days=3), True, 0, False),               # blocked right now: never overdue
        (TaskStatus.OPEN, NOW - timedelta(hours=1), False, 7200, False),          # 2 approved hours push it past now
        (TaskStatus.OPEN, NOW - timedelta(hours=1), False, 3600, False),          # exactly back to the deadline: not yet
        (TaskStatus.OPEN, NOW - timedelta(hours=1), False, 3599, True),           # one second short: overdue
    ],
)
def test_is_overdue(status, due_at, blocked, approved_seconds, expected):
    """Unfinished, not blocked, and past the real deadline (due_at plus approved blocked time), strictly."""
    assert is_overdue(_task(status, due_at, blocked, approved_seconds), NOW) is expected


@pytest.mark.asyncio
async def test_blocked_time_is_respected_and_the_flag_and_filter_still_agree(client, monkeypatch, db_session):
    """Blocked tasks and tasks with enough approved time are not overdue, in both the flag and the filter."""
    w = await _world(client, monkeypatch, "o2")
    await set_org_context(db_session, w.owner["organization"]["id"])
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    async def make(title) -> str:
        resp = await _create_task_via_api(client, w.hr, w.dispatch, title, due_at=one_hour_ago)
        return resp.json()["id"]

    plain_late = await make("Plain late")
    blocked_now = await make("Blocked right now")
    covered = await make("Two approved hours cover the delay")
    not_covered = await make("Half an hour approved is not enough")
    await db_session.execute(text("UPDATE tasks SET blocked_since = now() WHERE id = :id"), {"id": blocked_now})
    await db_session.execute(text("UPDATE tasks SET approved_blocked_seconds = 7200 WHERE id = :id"), {"id": covered})
    await db_session.execute(text("UPDATE tasks SET approved_blocked_seconds = 1800 WHERE id = :id"), {"id": not_covered})

    everything = await client.get(TASKS, headers=w.hr)
    only_overdue = await client.get(TASKS, params={"overdue": "true"}, headers=w.hr)
    only_not_overdue = await client.get(TASKS, params={"overdue": "false"}, headers=w.hr)

    flagged = {task["id"] for task in everything.json()["data"] if task["overdue"]}
    assert flagged == {plain_late, not_covered}
    assert set(_ids(only_overdue)) == flagged
    assert set(_ids(only_not_overdue)) == {blocked_now, covered}


@pytest.mark.asyncio
async def test_the_overdue_flag_and_the_overdue_filter_agree(client, monkeypatch):
    """The Python rule (the flag) and the database rule (the filter) pick the same tasks."""
    w = await _world(client, monkeypatch, "o1")

    async def make(title, due_at=None):
        resp = await _create_task_via_api(client, w.hr, w.dispatch, title, due_at=due_at)
        return resp.json()["id"]

    late_and_open = await make("Late and open", LONG_AGO)
    late_but_done = await make("Late but done", LONG_AGO)
    late_but_cancelled = await make("Late but cancelled", LONG_AGO)
    not_due_yet = await make("Not due yet", FAR_AHEAD)
    no_deadline = await make("No deadline")
    await client.post(f"{TASKS}/{late_but_done}/complete", headers=w.hr)
    await client.post(f"{TASKS}/{late_but_cancelled}/cancel", json={"reason": "Not needed"}, headers=w.hr)

    everything = await client.get(TASKS, headers=w.hr)
    only_overdue = await client.get(TASKS, params={"overdue": "true"}, headers=w.hr)
    only_not_overdue = await client.get(TASKS, params={"overdue": "false"}, headers=w.hr)

    flags = {task["id"]: task["overdue"] for task in everything.json()["data"]}
    ids_flagged_overdue = {task_id for task_id, flag in flags.items() if flag}
    assert ids_flagged_overdue == {late_and_open}
    assert set(_ids(only_overdue)) == ids_flagged_overdue
    assert set(_ids(only_not_overdue)) == {late_but_done, late_but_cancelled, not_due_yet, no_deadline}
    # The single-task endpoint tells the same story.
    one = await client.get(f"{TASKS}/{late_and_open}", headers=w.hr)
    assert one.json()["overdue"] is True
    assert (await client.get(f"{TASKS}/{not_due_yet}", headers=w.hr)).json()["overdue"] is False
