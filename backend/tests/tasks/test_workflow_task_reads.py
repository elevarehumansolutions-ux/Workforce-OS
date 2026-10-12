"""Tests for the read-only Task-module questions the Workflow module asks (M11).

``count_open_tasks_for_step``, ``workflow_instance_ids_for_assignee`` and
``list_tasks_for_workflow_instance``.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.tasks.service import TaskService
from tests.conftest import set_org_context
from tests.tasks.test_create_workflow_task import _create, _workflow_rows
from tests.tasks.test_tasks_router import TASKS, _task, _world
from tests.workflow.test_workflow_tables import _instance, _step


async def _second_case_and_step(db_session, world, first_step):
    """Another case and another step on the same template."""
    org_id = world.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    other_step = _step(org_id, first_step.workflow_template_id, world.sales, step_order=2, name="Legal check")
    other_case = _instance(org_id, first_step.workflow_template_id, subject="Acme Ltd")
    db_session.add_all([other_step, other_case])
    await db_session.flush()
    return other_step, other_case


@pytest.mark.asyncio
async def test_open_tasks_for_a_step_counts_open_and_in_progress_only(client, monkeypatch, db_session):
    """Two open, one in progress, one completed, one cancelled, one on another step: the count is 3."""
    w = await _world(client, monkeypatch, "wr1")
    step, case = await _workflow_rows(db_session, w)
    other_step, _ = await _second_case_and_step(db_session, w, step)
    open_one = await _create(db_session, w, step, case, title="Open one")
    await _create(db_session, w, step, case, title="Open two")
    in_progress = await _create(db_session, w, step, case, title="In progress")
    done = await _create(db_session, w, step, case, title="Done")
    cancelled = await _create(db_session, w, step, case, title="Cancelled")
    await _create(db_session, w, other_step, case, title="On another step")
    in_progress.status = "in_progress"
    await db_session.flush()
    assert (await client.post(f"{TASKS}/{done.id}/complete", headers=w.hr)).status_code == 200
    cancel = await client.post(f"{TASKS}/{cancelled.id}/cancel", json={"reason": "Not needed"}, headers=w.hr)
    assert cancel.status_code == 200
    await set_org_context(db_session, w.owner["organization"]["id"])

    service = TaskService(db_session)

    assert await service.count_open_tasks_for_step(step.id) == 3
    assert await service.count_open_tasks_for_step(other_step.id) == 1
    assert await service.count_open_tasks_for_step(uuid.uuid4()) == 0
    assert open_one.status == "open"


@pytest.mark.asyncio
async def test_cases_for_an_assignee_lists_each_case_once_whatever_the_task_status(client, monkeypatch, db_session):
    """Chidi has two tasks in one case (one completed) and none elsewhere; a standalone task adds nothing."""
    w = await _world(client, monkeypatch, "wr2")
    step, case = await _workflow_rows(db_session, w)
    other_step, other_case = await _second_case_and_step(db_session, w, step)
    chidi = uuid.UUID(w.chidi.employee_id)
    first = await _create(db_session, w, step, case, assigned_to_employee_id=chidi)
    await _create(db_session, w, other_step, case, assigned_to_employee_id=chidi)
    assert (await client.post(f"{TASKS}/{first.id}/complete", headers=w.hr)).status_code == 200
    assert (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.bola.employee_id)).status_code == 200
    await set_org_context(db_session, w.owner["organization"]["id"])

    service = TaskService(db_session)

    assert await service.workflow_instance_ids_for_assignee(chidi) == [case.id]
    assert await service.workflow_instance_ids_for_assignee(uuid.UUID(w.bola.employee_id)) == []
    assert await service.workflow_instance_ids_for_assignee(uuid.uuid4()) == []
    assert other_case.id not in await service.workflow_instance_ids_for_assignee(chidi)


@pytest.mark.asyncio
async def test_the_tasks_of_a_case_come_oldest_first_with_every_status(client, monkeypatch, db_session):
    """Completed and cancelled tasks are included; another case's and standalone tasks are not."""
    w = await _world(client, monkeypatch, "wr3")
    step, case = await _workflow_rows(db_session, w)
    other_step, other_case = await _second_case_and_step(db_session, w, step)
    first = await _create(db_session, w, step, case, title="First")
    second = await _create(db_session, w, other_step, case, title="Second")
    third = await _create(db_session, w, other_step, case, title="Third")
    await _create(db_session, w, step, other_case, title="Someone else's case")
    # A case's tasks are made in separate requests, so their creation times differ.
    # Inside one test everything shares a single transaction, where the database
    # clock stands still, so the times are set here the way real tasks would have them.
    start = datetime.now(UTC) - timedelta(hours=3)
    for position, task in enumerate((first, second, third)):
        task.created_at = start + timedelta(hours=position)
    await db_session.flush()
    assert (await client.post(f"{TASKS}/{first.id}/complete", headers=w.hr)).status_code == 200
    cancel = await client.post(f"{TASKS}/{second.id}/cancel", json={"reason": "Skipped"}, headers=w.hr)
    assert cancel.status_code == 200
    assert (await _task(client, w.hr, w.dispatch, title="Standalone")).status_code == 200
    await set_org_context(db_session, w.owner["organization"]["id"])

    tasks = await TaskService(db_session).list_tasks_for_workflow_instance(case.id)

    assert [(t.title, t.status) for t in tasks] == [
        ("First", "completed"), ("Second", "cancelled"), ("Third", "open"),
    ]
    assert third.status == "open"
    assert await TaskService(db_session).list_tasks_for_workflow_instance(uuid.uuid4()) == []
