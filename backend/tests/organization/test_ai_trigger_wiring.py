"""Which Org Structure writes fire the AI generation trigger.

Scenario: Adaeze creates a critical department, then a non-critical one,
then adds a position to each. Only the writes that could make a new
suggestion true should call the trigger — proven here by replacing the
trigger with a recorder, so no real Redis or Celery call happens.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login
import app.modules.organization.router as organization_router

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _fake_trigger(monkeypatch):
    calls = []

    async def fake(organization_id, **kwargs):
        calls.append(organization_id)
        return True

    monkeypatch.setattr(organization_router, "trigger_ai_suggestion_generation", fake)
    return calls


@pytest.mark.asyncio
async def test_creating_a_critical_department_fires_the_trigger(client, monkeypatch):
    """A department created is_critical=True is worth a generation run."""
    owner = await register_verified_and_login(client, email="trig_dept1@example.com")
    h = _auth_header(owner["access_token"])
    calls = _fake_trigger(monkeypatch)

    resp = await client.post(DEPARTMENTS, json={"name": "Operations", "is_critical": True}, headers=h)

    assert resp.status_code == 200
    assert calls == [uuid.UUID(owner["organization"]["id"])]


@pytest.mark.asyncio
async def test_creating_a_non_critical_department_does_not_fire_it(client, monkeypatch):
    """Nothing about a plain, non-critical department could produce a critical_position pick."""
    owner = await register_verified_and_login(client, email="trig_dept2@example.com")
    h = _auth_header(owner["access_token"])
    calls = _fake_trigger(monkeypatch)

    resp = await client.post(DEPARTMENTS, json={"name": "Finance", "is_critical": False}, headers=h)

    assert resp.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_marking_an_existing_department_critical_fires_the_trigger(client, monkeypatch):
    """Flipping Ops from non-critical to critical exposes new candidate positions."""
    owner = await register_verified_and_login(client, email="trig_dept3@example.com")
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    calls = _fake_trigger(monkeypatch)

    resp = await client.patch(
        f"{DEPARTMENTS}/{dept.json()['id']}", json={"is_critical": True}, headers=h
    )

    assert resp.status_code == 200
    assert calls == [uuid.UUID(owner["organization"]["id"])]


@pytest.mark.asyncio
async def test_an_unrelated_department_update_does_not_fire_it(client, monkeypatch):
    """Renaming a department, without touching is_critical, is not a generation-worthy change."""
    owner = await register_verified_and_login(client, email="trig_dept4@example.com")
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    calls = _fake_trigger(monkeypatch)

    resp = await client.patch(
        f"{DEPARTMENTS}/{dept.json()['id']}", json={"name": "Growth"}, headers=h
    )

    assert resp.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_adding_a_position_fires_the_trigger(client, monkeypatch):
    """Unconditional: whether the department is critical is checked two layers down.

    (no candidates -> no Claude call), so the router doesn't need an extra lookup here.
    """
    owner = await register_verified_and_login(client, email="trig_pos1@example.com")
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    calls = _fake_trigger(monkeypatch)

    resp = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "Dispatcher"}, headers=h
    )

    assert resp.status_code == 200
    assert calls == [uuid.UUID(owner["organization"]["id"])]
