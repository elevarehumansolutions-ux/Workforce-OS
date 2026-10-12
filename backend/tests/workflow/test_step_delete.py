"""Tests for DELETE /workflow-steps/{id} (M11 slice B, endpoint 6d).

Tasks are created from steps in slice D, so the tasks here are inserted
straight into the table.
"""
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.tasks.models import Task
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_step_add import _add
from tests.workflow.test_step_update import STEPS
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create


async def _template_with_steps(client, w, *names) -> tuple[dict, list[dict]]:
    """A template with one step per name, returned with the steps as JSON."""
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    steps = [(await _add(client, w.hr, template["id"], name, w.sales)).json() for name in names]
    return template, steps


async def _add_task(db_session, world, step_id: str, **changes) -> None:
    """Put a task made from the step straight into the table (default: open)."""
    org_id = world.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    fields = {
        "organization_id": uuid.UUID(org_id),
        "department_id": uuid.UUID(world.sales),
        "title": "Finance review for Zenith Ltd",
        "workflow_step_id": uuid.UUID(step_id),
    }
    fields.update(changes)
    db_session.add(Task(**fields))
    await db_session.flush()


@pytest.mark.asyncio
async def test_deleting_a_middle_step_closes_the_gap(client, monkeypatch):
    """Of A, B, C, D deleting B leaves A, C, D numbered 1, 2, 3; the audit entry records the old position."""
    w = await _world(client, monkeypatch, "sd1")
    template, steps = await _template_with_steps(client, w, "A", "B", "C", "D")

    deleted = await client.delete(f"{STEPS}/{steps[1]['id']}", headers=w.hr)

    assert deleted.status_code == 200 and deleted.json()["id"] == steps[1]["id"]
    live =(await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.hr)).json()
    assert [(s["step_order"], s["name"]) for s in live] == [(1, "A"), (2, "C"), (3, "D")]
    audit = await client.get(AUDIT, params={"entity_type": "workflow_step", "entity_id": steps[1]["id"]}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "delete")
    assert entry["changes"]["old"]["step_order"] == 2 and entry["changes"]["new"]["deleted_at"] is not None


@pytest.mark.asyncio
async def test_a_step_with_an_open_task_cannot_be_deleted(client, monkeypatch, db_session):
    """An open task and an in-progress task each block it (409, named); nothing is renumbered."""
    w = await _world(client, monkeypatch, "sd2")
    template, steps = await _template_with_steps(client, w, "A", "B", "C")
    await _add_task(db_session, w, steps[1]["id"])
    await _add_task(db_session, w, steps[1]["id"], status="in_progress")

    refused = await client.delete(f"{STEPS}/{steps[1]['id']}", headers=w.hr)

    assert refused.status_code == 409 and refused.json()["code"] == "RESOURCE_IN_USE"
    assert "2 task(s)" in refused.json()["message"]
    live = (await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.hr)).json()
    assert [(s["step_order"], s["name"]) for s in live] == [(1, "A"), (2, "B"), (3, "C")]


@pytest.mark.asyncio
async def test_finished_tasks_and_other_steps_tasks_do_not_block(client, monkeypatch, db_session):
    """A completed and a cancelled task on the step, and an open task on a different step, allow the delete."""
    w = await _world(client, monkeypatch, "sd3")
    template, steps = await _template_with_steps(client, w, "A", "B")
    await _add_task(db_session, w, steps[1]["id"], status="completed", completed_at=datetime.now(UTC))
    await _add_task(db_session, w, steps[1]["id"], status="cancelled", cancel_reason="Client withdrew")
    await _add_task(db_session, w, steps[0]["id"])

    deleted = await client.delete(f"{STEPS}/{steps[1]['id']}", headers=w.hr)

    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_the_only_step_can_be_deleted_leaving_an_empty_template(client, monkeypatch):
    """No special rule for the last step: the template is just empty again."""
    w = await _world(client, monkeypatch, "sd4")
    template, steps = await _template_with_steps(client, w, "Only")

    deleted = await client.delete(f"{STEPS}/{steps[0]['id']}", headers=w.hr)

    assert deleted.status_code == 200
    assert (await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.hr)).json() == []


@pytest.mark.asyncio
async def test_only_builders_delete_and_the_step_must_exist(client, monkeypatch):
    """An employee gets a 403 and the step survives; unknown or already deleted is a 404; a manager may delete."""
    w = await _world(client, monkeypatch, "sd5")
    template, steps = await _template_with_steps(client, w, "A", "B")
    url = f"{STEPS}/{steps[0]['id']}"

    by_employee = await client.delete(url, headers=w.chidi.h)
    by_manager = await client.delete(url, headers=w.sam.h)
    again = await client.delete(url, headers=w.hr)
    unknown = await client.delete(f"{STEPS}/00000000-0000-0000-0000-000000000000", headers=w.hr)

    assert by_employee.status_code == 403
    assert by_manager.status_code == 200
    assert again.status_code == 404 and unknown.status_code == 404
    live = (await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.hr)).json()
    assert [(s["step_order"], s["name"]) for s in live] == [(1, "B")]
