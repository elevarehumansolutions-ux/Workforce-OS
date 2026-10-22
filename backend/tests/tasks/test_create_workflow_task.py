"""Tests for TaskService.create_workflow_task, the entry point for the Workflow module (M11)."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import DepartmentNotFoundException
from app.modules.tasks.service import TaskService
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import AUDIT, NOTIFICATIONS, _world
from tests.workflow.test_workflow_tables import _instance, _step, _template

DUE = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)


async def _workflow_rows(db_session, world):
    """A template, one step and one running case, so a task can point at them."""
    org_id = world.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    template = _template(org_id, world.dispatch)
    db_session.add(template)
    await db_session.flush()
    step = _step(org_id, template.id, world.dispatch)
    case = _instance(org_id, template.id)
    db_session.add_all([step, case])
    await db_session.flush()
    return step, case


async def _create(db_session, world, step, case, **changes):
    """Call the method the way the Workflow module will."""
    await set_org_context(db_session, world.owner["organization"]["id"])
    arguments = {
        "organization_id": uuid.UUID(world.owner["organization"]["id"]),
        "department_id": uuid.UUID(world.dispatch),
        "title": "Finance review: Zenith Ltd",
        "due_at": DUE,
        "workflow_instance_id": case.id,
        "workflow_step_id": step.id,
    }
    arguments.update(changes)
    return await TaskService(db_session).create_workflow_task(**arguments)


async def _titles(client, headers) -> list[str]:
    response = await client.get(NOTIFICATIONS, headers=headers)
    return [n["title"] for n in response.json()]


@pytest.mark.asyncio
async def test_the_task_goes_to_the_default_assignee_and_has_no_human_creator(client, monkeypatch, db_session):
    """Chidi gets the task and a notification; it is linked to its case and step; the audit entry has no actor."""
    w = await _world(client, monkeypatch, "cw1")
    step, case = await _workflow_rows(db_session, w)

    task = await _create(
        db_session, w, step, case, assigned_to_employee_id=uuid.UUID(w.chidi.employee_id), description="Check the invoice"
    )

    assert task.assigned_to_employee_id == uuid.UUID(w.chidi.employee_id)
    assert task.created_by_user_id is None and task.status == "open"
    assert task.due_at == DUE and task.description == "Check the invoice"
    assert (task.workflow_instance_id, task.workflow_step_id) == (case.id, step.id)
    assert "New task: Finance review: Zenith Ltd" in await _titles(client, w.chidi.h)
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": str(task.id)}, headers=w.hr)
    entry = audit.json()["data"][0]
    assert entry["action"] == "create" and entry["actor_user_id"] is None
    assert entry["changes"]["new"]["workflow_step_id"] == str(step.id)


@pytest.mark.asyncio
async def test_no_default_assignee_means_unassigned_and_the_head_is_told(client, monkeypatch, db_session):
    """No assignee and no deadline are fine: the task waits in the queue and Tunde, the head of Dispatch, is asked to assign it."""
    w = await _world(client, monkeypatch, "cw2")
    step, case = await _workflow_rows(db_session, w)

    task = await _create(db_session, w, step, case, due_at=None)

    assert task.assigned_to_employee_id is None and task.due_at is None
    assert "A task for Dispatch needs an owner" in await _titles(client, w.tunde.h)
    assert "A task for Dispatch needs an owner" not in await _titles(client, w.chidi.h)


@pytest.mark.asyncio
async def test_an_offboarded_assignee_is_skipped_not_an_error(client, monkeypatch, db_session):
    """Bola left: the chain does not break, the task is unassigned and the head hears about it."""
    w = await _world(client, monkeypatch, "cw3")
    step, case = await _workflow_rows(db_session, w)
    await client.post(f"/api/v1/employees/{w.bola.employee_id}/offboard", headers=w.hr)

    task = await _create(db_session, w, step, case, assigned_to_employee_id=uuid.UUID(w.bola.employee_id))
    unknown = await _create(db_session, w, step, case, assigned_to_employee_id=uuid.uuid4())

    assert task.assigned_to_employee_id is None and unknown.assigned_to_employee_id is None
    assert "A task for Dispatch needs an owner" in await _titles(client, w.tunde.h)


@pytest.mark.asyncio
async def test_with_no_department_head_the_hr_administrators_are_told(client, monkeypatch, db_session):
    """Sales has no head, so HR gets the "needs an owner" notification."""
    w = await _world(client, monkeypatch, "cw4")
    step, case = await _workflow_rows(db_session, w)

    task = await _create(db_session, w, step, case, department_id=uuid.UUID(w.sales))

    assert task.assigned_to_employee_id is None
    assert "A task for Sales needs an owner" in await _titles(client, w.hr)


@pytest.mark.asyncio
async def test_a_department_from_another_organization_is_refused(client, monkeypatch, db_session):
    """The chain fails loudly rather than creating a task in a department that is not there."""
    w = await _world(client, monkeypatch, "cw5")
    other = await _world(client, monkeypatch, "cw6")
    step, case = await _workflow_rows(db_session, w)

    with pytest.raises(DepartmentNotFoundException):
        await _create(db_session, w, step, case, department_id=uuid.UUID(other.dispatch))


@pytest.mark.asyncio
async def test_the_new_task_is_an_ordinary_task_for_everything_else(client, monkeypatch, db_session):
    """The assignee sees it once clocked in, and the overdue rule applies like any task."""
    w = await _world(client, monkeypatch, "cw7")
    step, case = await _workflow_rows(db_session, w)
    late = datetime.now(UTC) - timedelta(hours=1)
    task = await _create(
        db_session, w, step, case, assigned_to_employee_id=uuid.UUID(w.chidi.employee_id), due_at=late
    )
    await client.post("/api/v1/attendance/clock-in", headers=w.chidi.h)

    seen = await client.get(f"/api/v1/tasks/{task.id}", headers=w.chidi.h)

    assert seen.status_code == 200
    assert seen.json()["overdue"] is True
    assert seen.json()["workflow_step_id"] == str(step.id)
