"""POST /notifications/read-by-link: opening a task directly clears its notification (the bell).

Scenario: HR gives Chidi a task, so his bell shows 1. He opens the task from his task list, not from the bell. The
bell must clear anyway, and must not touch anyone else's notifications or other tasks' notifications.
"""
import pytest

from app.modules.audit_and_notification.task_email import dispatch_task_email
from tests.tasks.test_tasks_router import DUE, NOTIFICATIONS, _task, _world

READ_BY_LINK = f"{NOTIFICATIONS}/read-by-link"
COUNT = f"{NOTIFICATIONS}/unread-count"


def _no_real_email(monkeypatch) -> None:
    monkeypatch.setattr(dispatch_task_email, "delay", lambda *args: None)


async def _give(client, w, person, title: str) -> str:
    resp = await _task(client, w.hr, w.dispatch, title=title, assigned_to_employee_id=person.employee_id, due_at=DUE)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_opening_a_task_marks_only_that_tasks_notification_read(client, monkeypatch):
    w = await _world(client, monkeypatch, "rl1")
    _no_real_email(monkeypatch)
    first = await _give(client, w, w.chidi, "First")
    await _give(client, w, w.chidi, "Second")
    assert (await client.get(COUNT, headers=w.chidi.h)).json() == {"unread": 2}

    resp = await client.post(READ_BY_LINK, json={"link_type": "task", "link_id": first}, headers=w.chidi.h)

    assert resp.status_code == 200 and resp.json() == {"marked_read": 1}
    assert (await client.get(COUNT, headers=w.chidi.h)).json() == {"unread": 1}


@pytest.mark.asyncio
async def test_it_is_harmless_to_repeat_and_for_an_unknown_task(client, monkeypatch):
    w = await _world(client, monkeypatch, "rl2")
    _no_real_email(monkeypatch)
    task = await _give(client, w, w.chidi, "Only")
    body = {"link_type": "task", "link_id": task}

    first = await client.post(READ_BY_LINK, json=body, headers=w.chidi.h)
    again = await client.post(READ_BY_LINK, json=body, headers=w.chidi.h)
    unknown = await client.post(
        READ_BY_LINK, json={"link_type": "task", "link_id": "00000000-0000-4000-8000-000000000000"}, headers=w.chidi.h
    )

    assert first.json() == {"marked_read": 1}
    assert again.json() == {"marked_read": 0} and unknown.json() == {"marked_read": 0}


@pytest.mark.asyncio
async def test_it_never_touches_someone_elses_notifications(client, monkeypatch):
    w = await _world(client, monkeypatch, "rl3")
    _no_real_email(monkeypatch)
    bolas_task = await _give(client, w, w.bola, "Bola's")

    resp = await client.post(READ_BY_LINK, json={"link_type": "task", "link_id": bolas_task}, headers=w.chidi.h)

    assert resp.json() == {"marked_read": 0}
    assert (await client.get(COUNT, headers=w.bola.h)).json() == {"unread": 1}


@pytest.mark.asyncio
async def test_it_needs_a_signed_in_person_and_a_valid_body(client, monkeypatch):
    w = await _world(client, monkeypatch, "rl4")

    assert (await client.post(READ_BY_LINK, json={"link_type": "task", "link_id": "x"})).status_code == 401
    bad = await client.post(READ_BY_LINK, json={"link_type": "task", "link_id": "not-a-uuid"}, headers=w.chidi.h)
    assert bad.status_code == 422
