"""Tests for PATCH /workflow-templates/{id} (M11 slice B, endpoint 3b)."""
import pytest

from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create


@pytest.mark.asyncio
async def test_hr_renames_a_template_and_the_old_name_is_audited(client, monkeypatch):
    """Only the name changes; the department stays; the audit entry shows old and new."""
    w = await _world(client, monkeypatch, "tu1")
    template = await _create(client, w.hr, "Onboarding", w.dispatch)

    updated = await client.patch(
        f"{TEMPLATES}/{template['id']}", json={"name": "  Client Onboarding "}, headers=w.hr
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == "Client Onboarding"
    assert updated.json()["department_id"] == w.dispatch
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_template", "entity_id": template["id"]}, headers=w.hr
    )
    entry = next(e for e in audit.json()["data"] if e["action"] == "update")
    assert entry["changes"] == {"old": {"name": "Onboarding"}, "new": {"name": "Client Onboarding"}}


@pytest.mark.asyncio
async def test_any_manager_may_edit_any_template_but_an_employee_may_not(client, monkeypatch):
    """Sam (Sales manager) edits a template HR built; Chidi (employee) gets a 403."""
    w = await _world(client, monkeypatch, "tu2")
    template = await _create(client, w.hr, "Onboarding", w.dispatch)

    by_manager = await client.patch(f"{TEMPLATES}/{template['id']}", json={"name": "Renamed"}, headers=w.sam.h)
    by_employee = await client.patch(f"{TEMPLATES}/{template['id']}", json={"name": "Hacked"}, headers=w.chidi.h)

    assert by_manager.status_code == 200 and by_manager.json()["name"] == "Renamed"
    assert by_employee.status_code == 403


@pytest.mark.asyncio
async def test_the_owning_department_can_change_but_must_exist_in_the_company(client, monkeypatch):
    """A real department of the company is accepted; an unknown or foreign one is a 404."""
    w = await _world(client, monkeypatch, "tu3")
    other = await _world(client, monkeypatch, "tu4")
    template = await _create(client, w.hr, "Onboarding", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    moved = await client.patch(url, json={"department_id": w.sales}, headers=w.hr)
    foreign = await client.patch(url, json={"department_id": other.dispatch}, headers=w.hr)

    assert moved.status_code == 200 and moved.json()["department_id"] == w.sales
    assert foreign.status_code == 404 and foreign.json()["code"] == "DEPARTMENT_NOT_FOUND"
    assert (await client.get(url, headers=w.hr)).json()["department_id"] == w.sales


@pytest.mark.asyncio
async def test_bad_edits_are_refused(client, monkeypatch):
    """A blank name or a null is a 422, and an unknown template is a 404."""
    w = await _world(client, monkeypatch, "tu5")
    template = await _create(client, w.hr, "Onboarding", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    blank = await client.patch(url, json={"name": "   "}, headers=w.hr)
    null_name = await client.patch(url, json={"name": None}, headers=w.hr)
    null_department = await client.patch(url, json={"department_id": None}, headers=w.hr)
    unknown = await client.patch(
        f"{TEMPLATES}/00000000-0000-0000-0000-000000000000", json={"name": "X"}, headers=w.hr
    )

    assert blank.status_code == 422
    assert null_name.status_code == 422 and null_department.status_code == 422
    assert unknown.status_code == 404
    assert (await client.get(url, headers=w.hr)).json()["name"] == "Onboarding"
