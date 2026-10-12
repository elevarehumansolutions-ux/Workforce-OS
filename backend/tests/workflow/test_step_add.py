"""Tests for POST /workflow-templates/{id}/steps (M11 slice B, endpoint 6a).

The step LIST endpoint comes next, so these tests read the steps straight
from the database through the shared test session.
"""
import uuid

import pytest
from sqlalchemy import select

from app.modules.workflow.models import WorkflowStep
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create


async def _add(client, headers, template_id: str, name: str, department_id: str, **extra):
    """Add a step through the API and return the raw response."""
    return await client.post(
        f"{TEMPLATES}/{template_id}/steps",
        json={"name": name, "department_id": department_id, **extra},
        headers=headers,
    )


async def _order(db_session, world, template_id: str) -> list[tuple[int, str]]:
    """The template's steps as (position, name), in position order."""
    await set_org_context(db_session, world.owner["organization"]["id"])
    result = await db_session.execute(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_template_id == uuid.UUID(template_id))
        .order_by(WorkflowStep.step_order)
    )
    return [(s.step_order, s.name) for s in result.scalars()]


@pytest.mark.asyncio
async def test_steps_added_without_a_position_go_to_the_end(client, monkeypatch, db_session):
    """Sales, Finance, Legal are added one after another and end up numbered 1, 2, 3."""
    w = await _world(client, monkeypatch, "sa1")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    first = await _add(client, w.hr, template["id"], "Sales hand-off", w.sales)
    await _add(client, w.hr, template["id"], "Finance review", w.dispatch, default_turnaround_hours=24)
    await _add(client, w.hr, template["id"], "Legal check", w.sales)

    assert first.status_code == 200
    body = first.json()
    assert body["step_order"] == 1 and body["workflow_template_id"] == template["id"]
    assert body["default_assignee_employee_id"] is None and body["default_turnaround_hours"] is None
    assert await _order(db_session, w, template["id"]) == [
        (1, "Sales hand-off"),
        (2, "Finance review"),
        (3, "Legal check"),
    ]


@pytest.mark.asyncio
async def test_a_step_added_in_the_middle_pushes_the_later_ones_down(client, monkeypatch, db_session):
    """Compliance at position 2 turns Finance (2) and Legal (3) into 3 and 4."""
    w = await _world(client, monkeypatch, "sa2")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    for name in ("Sales hand-off", "Finance review", "Legal check"):
        await _add(client, w.hr, template["id"], name, w.sales)

    inserted = await _add(client, w.hr, template["id"], "Compliance", w.sales, step_order=2)
    at_front = await _add(client, w.hr, template["id"], "Kick-off", w.sales, step_order=1)

    assert inserted.json()["step_order"] == 2 and at_front.json()["step_order"] == 1
    assert await _order(db_session, w, template["id"]) == [
        (1, "Kick-off"),
        (2, "Sales hand-off"),
        (3, "Compliance"),
        (4, "Finance review"),
        (5, "Legal check"),
    ]


@pytest.mark.asyncio
async def test_the_position_must_be_within_the_template(client, monkeypatch, db_session):
    """With two steps, 3 (the end) is fine and 9 is a 422; nothing is added by the refusal."""
    w = await _world(client, monkeypatch, "sa3")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _add(client, w.hr, template["id"], "One", w.sales)
    await _add(client, w.hr, template["id"], "Two", w.sales)

    too_far = await _add(client, w.hr, template["id"], "Nine", w.sales, step_order=9)
    zero = await _add(client, w.hr, template["id"], "Zero", w.sales, step_order=0)
    at_end = await _add(client, w.hr, template["id"], "Three", w.sales, step_order=3)

    assert too_far.status_code == 422 and "between 1 and 3" in too_far.json()["message"]
    assert zero.status_code == 422
    assert at_end.status_code == 200
    assert await _order(db_session, w, template["id"]) == [(1, "One"), (2, "Two"), (3, "Three")]


@pytest.mark.asyncio
async def test_the_default_assignee_and_turnaround_are_checked(client, monkeypatch):
    """A real active employee is accepted; unknown is a 404; offboarded or a non-positive turnaround is a 422."""
    w = await _world(client, monkeypatch, "sa4")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    ok = await _add(
        client, w.hr, template["id"], "Finance review", w.dispatch,
        default_assignee_employee_id=w.chidi.employee_id, default_turnaround_hours=24,
    )
    unknown = await _add(
        client, w.hr, template["id"], "Ghost", w.dispatch,
        default_assignee_employee_id="00000000-0000-0000-0000-000000000000",
    )
    await client.post(f"/api/v1/employees/{w.bola.employee_id}/offboard", headers=w.hr)
    offboarded = await _add(
        client, w.hr, template["id"], "Left", w.dispatch, default_assignee_employee_id=w.bola.employee_id
    )
    zero_hours = await _add(client, w.hr, template["id"], "Zero", w.dispatch, default_turnaround_hours=0)
    negative_hours = await _add(client, w.hr, template["id"], "Neg", w.dispatch, default_turnaround_hours=-3)

    assert ok.status_code == 200
    assert ok.json()["default_assignee_employee_id"] == w.chidi.employee_id
    assert ok.json()["default_turnaround_hours"] == 24
    assert unknown.status_code == 404 and unknown.json()["code"] == "EMPLOYEE_NOT_FOUND"
    assert offboarded.status_code == 422 and "offboarded" in offboarded.json()["message"]
    assert zero_hours.status_code == 422 and negative_hours.status_code == 422


@pytest.mark.asyncio
async def test_the_department_and_template_must_exist_and_only_builders_add(client, monkeypatch):
    """Unknown department or template is a 404; an employee gets a 403; a manager may add."""
    w = await _world(client, monkeypatch, "sa5")
    other = await _world(client, monkeypatch, "sa6")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    foreign_department = await _add(client, w.hr, template["id"], "Step", other.dispatch)
    unknown_template = await _add(client, w.hr, "00000000-0000-0000-0000-000000000000", "Step", w.sales)
    by_employee = await _add(client, w.chidi.h, template["id"], "Step", w.sales)
    by_manager = await _add(client, w.sam.h, template["id"], "Step", w.sales)
    blank_name = await _add(client, w.hr, template["id"], "   ", w.sales)

    assert foreign_department.status_code == 404 and foreign_department.json()["code"] == "DEPARTMENT_NOT_FOUND"
    assert unknown_template.status_code == 404
    assert by_employee.status_code == 403
    assert by_manager.status_code == 200
    assert blank_name.status_code == 422


@pytest.mark.asyncio
async def test_adding_a_step_is_audited_and_allowed_on_an_archived_template(client, monkeypatch):
    """The audit entry records the final position; archiving does not stop building."""
    w = await _world(client, monkeypatch, "sa7")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await client.post(f"{TEMPLATES}/{template['id']}/archive", headers=w.hr)

    added = await _add(client, w.hr, template["id"], "Finance review", w.dispatch, default_turnaround_hours=24)

    assert added.status_code == 200
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_step", "entity_id": added.json()["id"]}, headers=w.hr
    )
    entry = audit.json()["data"][0]
    assert entry["action"] == "create"
    assert entry["changes"]["new"]["step_order"] == 1
    assert entry["changes"]["new"]["name"] == "Finance review"
    assert entry["changes"]["new"]["workflow_template_id"] == template["id"]
