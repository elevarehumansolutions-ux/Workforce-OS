"""Tests for POST /workflow-templates (M11 slice B, endpoint 1)."""
import pytest

from tests.tasks.test_tasks_router import AUDIT, _world

TEMPLATES = "/api/v1/workflow-templates"


@pytest.mark.asyncio
async def test_hr_creates_a_template_and_it_is_audited(client, monkeypatch):
    """HR builds "Client Onboarding" owned by Dispatch; the creator and an audit entry are recorded."""
    w = await _world(client, monkeypatch, "wt1")

    created = await client.post(
        TEMPLATES, json={"name": "Client Onboarding", "department_id": w.dispatch}, headers=w.hr
    )

    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "Client Onboarding" and body["department_id"] == w.dispatch
    assert body["organization_id"] == w.owner["organization"]["id"]
    assert body["created_by_user_id"] == w.owner["user"]["id"]
    assert body["archived_at"] is None
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_template", "entity_id": body["id"]}, headers=w.hr
    )
    entries = audit.json()["data"]
    assert [e["action"] for e in entries] == ["create"]
    assert entries[0]["changes"]["new"]["name"] == "Client Onboarding"


@pytest.mark.asyncio
async def test_a_manager_can_create_a_template_but_an_employee_cannot(client, monkeypatch):
    """Dana (manager) may build; Chidi (employee) gets a 403."""
    w = await _world(client, monkeypatch, "wt2")
    body = {"name": "Client Onboarding", "department_id": w.sales}

    by_manager = await client.post(TEMPLATES, json=body, headers=w.dana.h)
    by_employee = await client.post(TEMPLATES, json=body, headers=w.chidi.h)

    assert by_manager.status_code == 200
    assert by_manager.json()["created_by_user_id"] == w.dana.user_id
    assert by_employee.status_code == 403


@pytest.mark.asyncio
async def test_the_department_must_belong_to_the_callers_organization(client, monkeypatch):
    """An unknown department, or one from another company, is a 404."""
    mine = await _world(client, monkeypatch, "wt3")
    other = await _world(client, monkeypatch, "wt4")

    unknown = await client.post(
        TEMPLATES,
        json={"name": "Client Onboarding", "department_id": "00000000-0000-0000-0000-000000000000"},
        headers=mine.hr,
    )
    someone_elses = await client.post(
        TEMPLATES, json={"name": "Client Onboarding", "department_id": other.dispatch}, headers=mine.hr
    )

    assert unknown.status_code == 404 and unknown.json()["code"] == "DEPARTMENT_NOT_FOUND"
    assert someone_elses.status_code == 404


@pytest.mark.asyncio
async def test_the_name_is_trimmed_and_cannot_be_empty(client, monkeypatch):
    """Spaces around a name are removed; a blank or very long name is a 422."""
    w = await _world(client, monkeypatch, "wt5")

    trimmed = await client.post(
        TEMPLATES, json={"name": "  Client Onboarding  ", "department_id": w.dispatch}, headers=w.hr
    )
    blank = await client.post(TEMPLATES, json={"name": "   ", "department_id": w.dispatch}, headers=w.hr)
    too_long = await client.post(
        TEMPLATES, json={"name": "x" * 201, "department_id": w.dispatch}, headers=w.hr
    )

    assert trimmed.json()["name"] == "Client Onboarding"
    assert blank.status_code == 422 and too_long.status_code == 422
