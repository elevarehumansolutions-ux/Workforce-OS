"""Tests for PATCH /workflow-steps/{id} (M11 slice B, endpoint 6c)."""
import pytest

from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create

STEPS = "/api/v1/workflow-steps"


async def _step(client, w, **extra) -> dict:
    """A template with one Finance review step (24 hours, Chidi), returned as the step JSON."""
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    added = await _add(
        client, w.hr, template["id"], "Finance review", w.dispatch,
        default_assignee_employee_id=w.chidi.employee_id, default_turnaround_hours=24, **extra,
    )
    assert added.status_code == 200
    return added.json()


@pytest.mark.asyncio
async def test_hr_changes_some_fields_and_the_rest_stay(client, monkeypatch):
    """Renaming and changing the turnaround leaves the department and assignee alone; the audit shows old and new."""
    w = await _world(client, monkeypatch, "su1")
    step = await _step(client, w)

    updated = await client.patch(
        f"{STEPS}/{step['id']}", json={"name": "  Finance sign-off ", "default_turnaround_hours": 48}, headers=w.hr
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Finance sign-off" and body["default_turnaround_hours"] == 48
    assert body["department_id"] == w.dispatch and body["default_assignee_employee_id"] == w.chidi.employee_id
    assert body["step_order"] == 1
    audit = await client.get(AUDIT, params={"entity_type": "workflow_step", "entity_id": step["id"]}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "update")
    assert entry["changes"] == {
        "old": {"name": "Finance review", "default_turnaround_hours": 24},
        "new": {"name": "Finance sign-off", "default_turnaround_hours": 48},
    }


@pytest.mark.asyncio
async def test_null_clears_the_assignee_and_the_turnaround(client, monkeypatch):
    """Sending null removes the default assignee and the deadline; leaving the key out does not."""
    w = await _world(client, monkeypatch, "su2")
    step = await _step(client, w)
    url = f"{STEPS}/{step['id']}"

    untouched = await client.patch(url, json={"name": "Finance review"}, headers=w.hr)
    cleared = await client.patch(
        url, json={"default_assignee_employee_id": None, "default_turnaround_hours": None}, headers=w.hr
    )

    assert untouched.json()["default_assignee_employee_id"] == w.chidi.employee_id
    assert untouched.json()["default_turnaround_hours"] == 24
    assert cleared.status_code == 200
    assert cleared.json()["default_assignee_employee_id"] is None
    assert cleared.json()["default_turnaround_hours"] is None


@pytest.mark.asyncio
async def test_a_new_assignee_department_and_turnaround_are_checked(client, monkeypatch):
    """Offboarded or unknown people, foreign departments and non-positive hours are refused; the step is unchanged."""
    w = await _world(client, monkeypatch, "su3")
    other = await _world(client, monkeypatch, "su4")
    step = await _step(client, w)
    url = f"{STEPS}/{step['id']}"
    await client.post(f"/api/v1/employees/{w.bola.employee_id}/offboard", headers=w.hr)

    offboarded = await client.patch(url, json={"default_assignee_employee_id": w.bola.employee_id}, headers=w.hr)
    unknown = await client.patch(
        url, json={"default_assignee_employee_id": "00000000-0000-0000-0000-000000000000"}, headers=w.hr
    )
    foreign = await client.patch(url, json={"department_id": other.dispatch}, headers=w.hr)
    zero = await client.patch(url, json={"default_turnaround_hours": 0}, headers=w.hr)
    moved = await client.patch(
        url, json={"department_id": w.sales, "default_assignee_employee_id": w.tunde.employee_id}, headers=w.hr
    )

    assert offboarded.status_code == 422 and "offboarded" in offboarded.json()["message"]
    assert unknown.status_code == 404 and unknown.json()["code"] == "EMPLOYEE_NOT_FOUND"
    assert foreign.status_code == 404 and foreign.json()["code"] == "DEPARTMENT_NOT_FOUND"
    assert zero.status_code == 422
    assert moved.status_code == 200 and moved.json()["department_id"] == w.sales
    assert moved.json()["default_assignee_employee_id"] == w.tunde.employee_id


@pytest.mark.asyncio
async def test_required_fields_cannot_be_nulled_or_blanked_and_position_is_not_editable(client, monkeypatch):
    """Null or blank name, null department: 422. A step_order in the body is ignored, the position does not move."""
    w = await _world(client, monkeypatch, "su5")
    step = await _step(client, w)
    url = f"{STEPS}/{step['id']}"

    null_name = await client.patch(url, json={"name": None}, headers=w.hr)
    blank = await client.patch(url, json={"name": "   "}, headers=w.hr)
    null_department = await client.patch(url, json={"department_id": None}, headers=w.hr)
    position = await client.patch(url, json={"step_order": 5}, headers=w.hr)

    assert null_name.status_code == 422 and blank.status_code == 422 and null_department.status_code == 422
    assert position.status_code == 200 and position.json()["step_order"] == 1


@pytest.mark.asyncio
async def test_only_builders_edit_and_the_step_must_exist(client, monkeypatch):
    """A manager may edit; an employee gets a 403; unknown, other-company and deleted-template steps are 404."""
    w = await _world(client, monkeypatch, "su6")
    other = await _world(client, monkeypatch, "su7")
    step = await _step(client, w)
    theirs = await _step(client, other)
    url = f"{STEPS}/{step['id']}"

    by_employee = await client.patch(url, json={"name": "Hacked"}, headers=w.chidi.h)
    by_manager = await client.patch(url, json={"name": "Renamed"}, headers=w.sam.h)
    unknown = await client.patch(f"{STEPS}/00000000-0000-0000-0000-000000000000", json={"name": "X"}, headers=w.hr)
    someone_elses = await client.patch(f"{STEPS}/{theirs['id']}", json={"name": "X"}, headers=w.hr)
    await client.delete(f"{TEMPLATES}/{step['workflow_template_id']}", headers=w.hr)
    after_template_deleted = await client.patch(url, json={"name": "Late"}, headers=w.hr)

    assert by_employee.status_code == 403
    assert by_manager.status_code == 200 and by_manager.json()["name"] == "Renamed"
    assert unknown.status_code == 404 and unknown.json()["code"] == "WORKFLOW_STEP_NOT_FOUND"
    assert someone_elses.status_code == 404
    assert after_template_deleted.status_code == 404
