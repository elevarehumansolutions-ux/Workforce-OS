"""Tests for the overdue rule (M10 slice C), the Python form.

The SQL form is checked against the same cases through ``?overdue=true`` once
the filter is wired, so the two forms can't drift apart.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.tasks.enums import TaskStatus
from app.modules.tasks.models import Task
from app.modules.tasks.overdue import is_overdue
from tests.tasks.test_tasks_router import TASKS, _ids, _world
from tests.tasks.test_tasks_router import _task as _create_task_via_api

LONG_AGO = "2020-01-01T00:00:00+00:00"
FAR_AHEAD = "2099-01-01T00:00:00+00:00"

NOW = datetime(2026, 10, 8, 17, 0, 0, tzinfo=UTC)


def _task(status: TaskStatus, due_at: datetime | None) -> Task:
    return Task(status=status.value, due_at=due_at)


@pytest.mark.parametrize(
    "status, due_at, expected",
    [
        (TaskStatus.OPEN, NOW - timedelta(seconds=1), True),            # one second late
        (TaskStatus.IN_PROGRESS, NOW - timedelta(days=3), True),
        (TaskStatus.OPEN, NOW, False),                                  # exactly at the deadline: not yet
        (TaskStatus.OPEN, NOW + timedelta(seconds=1), False),
        (TaskStatus.OPEN, None, False),                                 # no deadline is never overdue
        (TaskStatus.COMPLETED, NOW - timedelta(days=3), False),         # finished work isn't overdue
        (TaskStatus.CANCELLED, NOW - timedelta(days=3), False),         # cancelled is neither done nor late
    ],
)
def test_is_overdue(status, due_at, expected):
    """Unfinished and past the deadline, strictly; everything else is not overdue."""
    assert is_overdue(_task(status, due_at), NOW) is expected


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
