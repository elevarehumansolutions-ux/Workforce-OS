"""Tests for to-do 67: a task cannot be created with, or changed to, a deadline that has passed.

Before this, someone could set a deadline of 10:45 when it was 11:30 and the task was overdue
the moment it was saved. Only a CHANGED deadline is checked on edit, so an already-overdue task
can still be renamed.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import TASKS, _ids, _task, _world

PAST = "2020-01-01T00:00:00+00:00"


def _in_one_hour() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat()


async def _make_overdue(db_session, w, task_id: str) -> None:
    """Move a task's deadline into the past directly in the database (the API refuses to)."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(
        text("UPDATE tasks SET due_at = now() - interval '2 hours' WHERE id = :id"), {"id": task_id}
    )


@pytest.mark.asyncio
async def test_creating_a_task_with_a_past_deadline_is_refused_on_the_deadline_field(client, monkeypatch):
    """422, the message is attached to due_at, and no task is made."""
    w = await _world(client, monkeypatch, "pd1")

    refused = await _task(client, w.hr, w.dispatch, "Too late", due_at=PAST)
    listed = await client.get(TASKS, headers=w.hr)

    assert refused.status_code == 422
    body = refused.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["details"][0]["field"] == "due_at"
    assert "must be in the future" in body["message"]
    assert _ids(listed) == []


@pytest.mark.asyncio
async def test_a_future_deadline_and_no_deadline_are_both_still_fine(client, monkeypatch):
    """The rule only refuses a time that has passed."""
    w = await _world(client, monkeypatch, "pd2")

    with_deadline = await _task(client, w.hr, w.dispatch, "Has a deadline", due_at=_in_one_hour())
    without_deadline = await _task(client, w.hr, w.dispatch, "No deadline")

    assert with_deadline.status_code == 200
    assert without_deadline.status_code == 200


@pytest.mark.asyncio
async def test_changing_a_deadline_to_a_past_time_is_refused_and_the_old_one_stays(client, monkeypatch):
    """Editing a task cannot move its deadline into the past."""
    w = await _world(client, monkeypatch, "pd3")
    created = (await _task(client, w.hr, w.dispatch, "Edit me", due_at=_in_one_hour())).json()

    refused = await client.patch(f"{TASKS}/{created['id']}", json={"due_at": PAST}, headers=w.hr)
    after = await client.get(f"{TASKS}/{created['id']}", headers=w.hr)

    assert refused.status_code == 422
    assert refused.json()["details"][0]["field"] == "due_at"
    assert after.json()["due_at"] == created["due_at"]


@pytest.mark.asyncio
async def test_an_overdue_task_can_still_be_renamed_and_keeps_its_deadline(client, monkeypatch, db_session):
    """Only a changed deadline is checked: saving a new title, or the same deadline again, works."""
    w = await _world(client, monkeypatch, "pd4")
    created = (await _task(client, w.hr, w.dispatch, "Old title", due_at=_in_one_hour())).json()
    await _make_overdue(db_session, w, created["id"])
    overdue = (await client.get(f"{TASKS}/{created['id']}", headers=w.hr)).json()

    renamed = await client.patch(f"{TASKS}/{created['id']}", json={"title": "New title"}, headers=w.hr)
    same_deadline = await client.patch(
        f"{TASKS}/{created['id']}", json={"title": "Newer title", "due_at": overdue["due_at"]}, headers=w.hr
    )

    assert overdue["overdue"] is True
    assert renamed.status_code == 200 and renamed.json()["title"] == "New title"
    assert same_deadline.status_code == 200 and same_deadline.json()["title"] == "Newer title"


@pytest.mark.asyncio
async def test_removing_a_deadline_is_still_allowed(client, monkeypatch):
    """Sending no deadline (null) clears it; that is not a past time."""
    w = await _world(client, monkeypatch, "pd5")
    created = (await _task(client, w.hr, w.dispatch, "Clear me", due_at=_in_one_hour())).json()

    cleared = await client.patch(f"{TASKS}/{created['id']}", json={"due_at": None}, headers=w.hr)

    assert cleared.status_code == 200
    assert cleared.json()["due_at"] is None
