"""Tests for cancelling and reassigning tasks (M10 slice B).

Same company as ``test_tasks_router``: Tunde heads Dispatch, Chidi and Bola are
Dispatch employees, Dana is a Dispatch ``manager``, Sam a Sales ``manager``,
Sales has no head, Adaeze is HR (08_DECISIONS.md 2026-10-07).
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.modules.tasks.enums import TaskStatus
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import (
    AUDIT,
    DUE,
    NOTIFICATIONS,
    TASKS,
    _clock_in,
    _task,
    _world,
)

NEW_DUE = "2099-01-01T10:00:00+00:00"


def _titles(resp) -> list[str]:
    return [n["title"] for n in resp.json()]


@pytest.mark.asyncio
async def test_who_can_cancel_a_task(client, monkeypatch):
    """HR, the head and the creator can; the assignee and a mere viewer cannot."""
    w = await _world(client, monkeypatch, "b1")
    await _clock_in(client, w.chidi)
    tid = (await _task(client, w.hr, w.dispatch, "Old job", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    url = f"{TASKS}/{tid}/cancel"
    body = {"reason": "Customer withdrew the order"}

    by_assignee = await client.post(url, json=body, headers=w.chidi.h)
    by_viewer = await client.post(url, json=body, headers=w.dana.h)   # sees Dispatch, didn't create it
    by_head = await client.post(url, json=body, headers=w.tunde.h)
    dana_made = (await _task(client, w.dana.h, w.dispatch, "Dana's job")).json()["id"]
    by_creator = await client.post(f"{TASKS}/{dana_made}/cancel", json=body, headers=w.dana.h)
    hr_made = (await _task(client, w.hr, w.dispatch, "HR's job")).json()["id"]
    by_hr = await client.post(f"{TASKS}/{hr_made}/cancel", json=body, headers=w.hr)

    assert by_assignee.status_code == 403 and by_assignee.json()["code"] == "PERMISSION_DENIED"
    assert by_viewer.status_code == 403
    assert by_head.status_code == by_creator.status_code == by_hr.status_code == 200
    assert by_head.json()["status"] == "cancelled"
    assert by_head.json()["cancel_reason"] == "Customer withdrew the order"
    assert by_head.json()["completed_at"] is None


@pytest.mark.asyncio
async def test_cancel_needs_a_reason(client, monkeypatch):
    """A missing, blank or oversized reason is refused and the task stays open."""
    w = await _world(client, monkeypatch, "b2")
    tid = (await _task(client, w.hr, w.dispatch)).json()["id"]
    url = f"{TASKS}/{tid}/cancel"

    missing = await client.post(url, json={}, headers=w.hr)
    blank = await client.post(url, json={"reason": "   "}, headers=w.hr)
    too_long = await client.post(url, json={"reason": "x" * 501}, headers=w.hr)
    extra = await client.post(url, json={"reason": "ok", "status": "open"}, headers=w.hr)

    assert missing.status_code == blank.status_code == too_long.status_code == extra.status_code == 422
    assert (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()["status"] == "open"


@pytest.mark.asyncio
async def test_cancel_is_final_and_leaves_a_trail(client, monkeypatch):
    """Cancelled tasks can't be cancelled again, completed, edited or reassigned; the assignee is told; it is audited."""
    w = await _world(client, monkeypatch, "b3")
    tid = (await _task(client, w.hr, w.dispatch, "Ship it", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    first = await client.post(f"{TASKS}/{tid}/cancel", json={"reason": "No longer needed"}, headers=w.hr)
    again = await client.post(f"{TASKS}/{tid}/cancel", json={"reason": "Twice"}, headers=w.hr)
    complete = await client.post(f"{TASKS}/{tid}/complete", headers=w.hr)
    edit = await client.patch(f"{TASKS}/{tid}", json={"title": "Zombie"}, headers=w.hr)
    reassign = await client.post(
        f"{TASKS}/{tid}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": NEW_DUE},
        headers=w.hr,
    )
    cancelled_list = await client.get(TASKS, params={"status": "cancelled"}, headers=w.hr)

    assert first.status_code == 200
    for refused in (again, complete, edit, reassign):
        assert refused.status_code == 409 and refused.json()["code"] == "TASK_NOT_OPEN"
    assert [t["id"] for t in cancelled_list.json()["data"]] == [tid]
    assert "Task cancelled: Ship it" in _titles(await client.get(NOTIFICATIONS, headers=w.chidi.h))
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": tid}, headers=w.hr)
    cancel_entries = [e for e in audit.json()["data"] if e["action"] == "cancel"]
    assert len(cancel_entries) == 1
    assert cancel_entries[0]["changes"]["new"]["cancel_reason"] == "No longer needed"
    assert cancel_entries[0]["changes"]["old"]["status"] == "open"


@pytest.mark.asyncio
async def test_a_completed_task_cannot_be_cancelled(client, monkeypatch):
    """Finished work stays finished."""
    w = await _world(client, monkeypatch, "b4")
    tid = (await _task(client, w.hr, w.dispatch)).json()["id"]
    await client.post(f"{TASKS}/{tid}/complete", headers=w.hr)

    resp = await client.post(f"{TASKS}/{tid}/cancel", json={"reason": "Oops"}, headers=w.hr)

    assert resp.status_code == 409 and resp.json()["code"] == "TASK_NOT_OPEN"
    assert (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()["status"] == "completed"


@pytest.mark.asyncio
async def test_someone_who_cannot_see_the_task_gets_a_404_not_a_403(client, monkeypatch):
    """Existence isn't revealed to people outside the task's view."""
    w = await _world(client, monkeypatch, "b5")
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.bola.employee_id)).json()["id"]

    cancel = await client.post(f"{TASKS}/{tid}/cancel", json={"reason": "x"}, headers=w.chidi.h)
    reassign = await client.post(
        f"{TASKS}/{tid}/reassign",
        json={"assigned_to_employee_id": w.chidi.employee_id, "due_at": NEW_DUE},
        headers=w.chidi.h,
    )

    assert cancel.status_code == reassign.status_code == 404


@pytest.mark.asyncio
async def test_reassigning_gives_the_new_person_a_fresh_deadline(client, monkeypatch):
    """Chidi -> Bola: new assignee and deadline, both are told, and it is audited with old and new."""
    w = await _world(client, monkeypatch, "b6")
    tid = (await _task(client, w.hr, w.dispatch, "Fix route", assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)).json()["id"]

    resp = await client.post(
        f"{TASKS}/{tid}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": NEW_DUE},
        headers=w.tunde.h,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["assigned_to_employee_id"] == w.bola.employee_id
    assert body["due_at"].startswith("2099-01-01") and body["status"] == "open"
    assert "New task: Fix route" in _titles(await client.get(NOTIFICATIONS, headers=w.bola.h))
    assert "Task reassigned: Fix route" in _titles(await client.get(NOTIFICATIONS, headers=w.chidi.h))
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": tid}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "reassign")
    assert entry["changes"]["old"]["assigned_to_employee_id"] == w.chidi.employee_id
    assert entry["changes"]["old"]["due_at"].startswith("2026-12-01")
    assert entry["changes"]["new"]["assigned_to_employee_id"] == w.bola.employee_id
    assert entry["changes"]["new"]["due_at"].startswith("2099-01-01")


@pytest.mark.asyncio
async def test_reassign_is_refused_for_bad_input(client, monkeypatch):
    """Past or naive deadline, no deadline, same person, offboarded or unknown person, extra fields."""
    w = await _world(client, monkeypatch, "b7")
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    url = f"{TASKS}/{tid}/reassign"
    await client.post(f"/api/v1/employees/{w.dana.employee_id}/offboard", headers=w.hr)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    past = await client.post(url, json={"assigned_to_employee_id": w.bola.employee_id, "due_at": yesterday}, headers=w.hr)
    naive = await client.post(url, json={"assigned_to_employee_id": w.bola.employee_id, "due_at": "2099-01-01T10:00:00"}, headers=w.hr)
    no_due = await client.post(url, json={"assigned_to_employee_id": w.bola.employee_id}, headers=w.hr)
    same = await client.post(url, json={"assigned_to_employee_id": w.chidi.employee_id, "due_at": NEW_DUE}, headers=w.hr)
    offboarded = await client.post(url, json={"assigned_to_employee_id": w.dana.employee_id, "due_at": NEW_DUE}, headers=w.hr)
    unknown = await client.post(url, json={"assigned_to_employee_id": str(uuid.uuid4()), "due_at": NEW_DUE}, headers=w.hr)
    extra = await client.post(url, json={"assigned_to_employee_id": w.bola.employee_id, "due_at": NEW_DUE, "status": "open"}, headers=w.hr)

    for refused in (past, naive, no_due, same, offboarded, extra):
        assert refused.status_code == 422
    assert unknown.status_code == 404 and unknown.json()["code"] == "EMPLOYEE_NOT_FOUND"
    still = (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()
    assert still["assigned_to_employee_id"] == w.chidi.employee_id


@pytest.mark.asyncio
async def test_who_can_reassign(client, monkeypatch):
    """HR, the head and the creator-in-department can; the assignee, a viewer and an outsider creator cannot."""
    w = await _world(client, monkeypatch, "b8")
    await _clock_in(client, w.chidi)
    payload = {"assigned_to_employee_id": w.bola.employee_id, "due_at": NEW_DUE}
    hr_made = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    dana_made = (await _task(client, w.dana.h, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    sam_made = (await _task(client, w.sam.h, w.dispatch)).json()["id"]    # lands on Tunde

    assignee = await client.post(f"{TASKS}/{hr_made}/reassign", json=payload, headers=w.chidi.h)
    viewer = await client.post(f"{TASKS}/{hr_made}/reassign", json=payload, headers=w.dana.h)
    outsider_creator = await client.post(
        f"{TASKS}/{sam_made}/reassign",
        json={"assigned_to_employee_id": w.chidi.employee_id, "due_at": NEW_DUE},
        headers=w.sam.h,
    )
    by_head = await client.post(f"{TASKS}/{hr_made}/reassign", json=payload, headers=w.tunde.h)
    by_creator = await client.post(f"{TASKS}/{dana_made}/reassign", json=payload, headers=w.dana.h)
    by_hr = await client.post(
        f"{TASKS}/{sam_made}/reassign",
        json={"assigned_to_employee_id": w.chidi.employee_id, "due_at": NEW_DUE},
        headers=w.hr,
    )

    for refused in (assignee, viewer, outsider_creator):
        assert refused.status_code == 403 and refused.json()["code"] == "PERMISSION_DENIED"
    assert by_head.status_code == by_creator.status_code == by_hr.status_code == 200


@pytest.mark.asyncio
async def test_an_unassigned_task_is_assigned_with_the_same_endpoint(client, monkeypatch):
    """Sales has no head: Dana's request is unassigned until HR picks someone, and only the new person is told."""
    w = await _world(client, monkeypatch, "b9")
    tid = (await _task(client, w.dana.h, w.sales, "Quote for Acme")).json()["id"]
    assert (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()["assigned_to_employee_id"] is None

    resp = await client.post(
        f"{TASKS}/{tid}/reassign",
        json={"assigned_to_employee_id": w.sam.employee_id, "due_at": NEW_DUE},
        headers=w.hr,
    )

    assert resp.status_code == 200 and resp.json()["assigned_to_employee_id"] == w.sam.employee_id
    assert "New task: Quote for Acme" in _titles(await client.get(NOTIFICATIONS, headers=w.sam.h))
    assert not [t for t in _titles(await client.get(NOTIFICATIONS, headers=w.bola.h)) if "Quote" in t]
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": tid}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "reassign")
    assert entry["changes"]["old"]["assigned_to_employee_id"] is None


@pytest.mark.asyncio
async def test_the_atomic_reassign_loses_cleanly_to_a_concurrent_change(client, monkeypatch, db_session):
    """If the assignee changed (or the task closed) since the caller read it, nothing is written; in_progress resets to open."""
    w = await _world(client, monkeypatch, "b10")
    org_id = w.owner["organization"]["id"]
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    await set_org_context(db_session, org_id)
    repo = TaskRepository(db_session)
    when = datetime(2099, 1, 1, tzinfo=UTC)
    task_uuid = uuid.UUID(tid)
    await db_session.execute(update(Task).where(Task.id == task_uuid).values(status=TaskStatus.IN_PROGRESS.value))

    stale = await repo.reassign_task(task_uuid, uuid.UUID(w.bola.employee_id), uuid.UUID(w.tunde.employee_id), when)
    fresh = await repo.reassign_task(task_uuid, uuid.UUID(w.chidi.employee_id), uuid.UUID(w.bola.employee_id), when)
    # The repository returns the one identity-mapped object, so read it before the next UPDATE.
    assert fresh is not None
    status_after_reassign, assignee_after_reassign = fresh.status, str(fresh.assigned_to_employee_id)
    after_close = await repo.cancel_task(task_uuid, "closed meanwhile")
    too_late = await repo.reassign_task(task_uuid, uuid.UUID(w.bola.employee_id), uuid.UUID(w.tunde.employee_id), when)

    assert stale is None
    assert status_after_reassign == TaskStatus.OPEN.value
    assert assignee_after_reassign == w.bola.employee_id
    assert after_close is not None and too_late is None
