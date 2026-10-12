"""Tests for the handover of an offboarded employee's open tasks (M10, 08_DECISIONS.md 2026-10-09).

The scan (every 10 minutes) finds open tasks assigned to an inactive employee,
ends their blocks, unassigns them, and tells the department head (or HR).
Nothing in the Organization module is involved: the Task module reacts to the
employee's status.
"""
import uuid

import pytest

from app.modules.tasks.repository import TaskRepository
from tests.conftest import set_org_context
from tests.tasks.test_overdue_scan import _run_scan_for
from tests.tasks.test_tasks_router import AUDIT, NOTIFICATIONS, TASKS, _clock_in, _task, _world

EMPLOYEES = "/api/v1/employees"
BLOCK = {"category": "external_dependency", "reason": "Waiting for the supplier"}


async def _handover_titles(client, headers) -> list[str]:
    """The 'X left: N task(s) need a new owner' notifications a person has received."""
    resp = await client.get(NOTIFICATIONS, headers=headers)
    return [n["title"] for n in resp.json() if "need a new owner" in n["title"]]


async def _offboard(client, w, person):
    resp = await client.post(f"{EMPLOYEES}/{person.employee_id}/offboard", headers=w.hr)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_open_tasks_of_someone_who_left_go_back_to_the_department_queue(client, monkeypatch, db_session):
    """Chidi leaves with 4 tasks: the 2 open ones are handed over, the finished and cancelled ones stay as history."""
    w = await _world(client, monkeypatch, "oh1")
    await _clock_in(client, w.chidi)
    ids = {}
    for title in ("Plain", "Stuck", "Done", "Dropped"):
        resp = await _task(client, w.hr, w.dispatch, title, assigned_to_employee_id=w.chidi.employee_id)
        ids[title] = resp.json()["id"]
    await client.post(f"{TASKS}/{ids['Stuck']}/block", json=BLOCK, headers=w.chidi.h)
    await client.post(f"{TASKS}/{ids['Done']}/complete", headers=w.hr)
    await client.post(f"{TASKS}/{ids['Dropped']}/cancel", json={"reason": "Not needed"}, headers=w.hr)
    await _offboard(client, w, w.chidi)

    await _run_scan_for(db_session, w)

    now = {title: (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json() for title, tid in ids.items()}
    assert now["Plain"]["assigned_to_employee_id"] is None and now["Plain"]["status"] == "open"
    assert now["Stuck"]["assigned_to_employee_id"] is None and now["Stuck"]["blocked_since"] is None
    assert now["Done"]["assigned_to_employee_id"] == w.chidi.employee_id          # history stays on his name
    assert now["Dropped"]["assigned_to_employee_id"] == w.chidi.employee_id
    block = (await client.get(f"{TASKS}/{ids['Stuck']}/blocks", headers=w.hr)).json()[0]
    assert block["unblocked_at"] is not None and block["review_status"] == "pending"
    assert await _handover_titles(client, w.tunde.h) == ["Chidi Tester left: 2 task(s) need a new owner"]
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": ids["Plain"]}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "unassign")
    assert entry["changes"]["old"]["assigned_to_employee_id"] == w.chidi.employee_id
    assert entry["changes"]["new"]["assigned_to_employee_id"] is None


@pytest.mark.asyncio
async def test_the_handover_happens_once_and_the_head_can_then_reassign(client, monkeypatch, db_session):
    """A second scan finds nothing to do; Tunde gives the orphaned task to Bola with a new deadline."""
    w = await _world(client, monkeypatch, "oh2")
    tid = (await _task(client, w.hr, w.dispatch, "Orphan", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    await _offboard(client, w, w.chidi)

    await _run_scan_for(db_session, w)
    await _run_scan_for(db_session, w)
    reassigned = await client.post(
        f"{TASKS}/{tid}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": "2099-01-01T10:00:00+00:00"},
        headers=w.tunde.h,
    )

    assert len(await _handover_titles(client, w.tunde.h)) == 1            # told once, not twice
    assert reassigned.status_code == 200 and reassigned.json()["assigned_to_employee_id"] == w.bola.employee_id


@pytest.mark.asyncio
async def test_with_no_department_head_hr_is_told(client, monkeypatch, db_session):
    """Sam leaves Sales (no head): the HR administrator hears about his task."""
    w = await _world(client, monkeypatch, "oh3")
    await _task(client, w.hr, w.sales, "Quote for Acme", assigned_to_employee_id=w.sam.employee_id)
    await _offboard(client, w, w.sam)

    await _run_scan_for(db_session, w)

    assert await _handover_titles(client, w.hr) == ["Sam Tester left: 1 task(s) need a new owner"]
    assert await _handover_titles(client, w.tunde.h) == []        # heads a different department


@pytest.mark.asyncio
async def test_the_lookup_finds_an_organization_only_while_orphaned_work_exists(client, monkeypatch, db_session):
    """The scan is queued for the organization until the handover is done, and not after."""
    w = await _world(client, monkeypatch, "oh4")
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await _task(client, w.hr, w.dispatch, "Orphan", assigned_to_employee_id=w.chidi.employee_id)
    repo = TaskRepository(db_session)

    await set_org_context(db_session, uuid.uuid4())
    before_leaving = await repo.list_organizations_needing_scan()
    await _offboard(client, w, w.chidi)
    await set_org_context(db_session, uuid.uuid4())
    after_leaving = await repo.list_organizations_needing_scan()
    await _run_scan_for(db_session, w)
    await set_org_context(db_session, uuid.uuid4())
    after_handover = await repo.list_organizations_needing_scan()

    assert org_id not in before_leaving
    assert org_id in after_leaving
    assert org_id not in after_handover
