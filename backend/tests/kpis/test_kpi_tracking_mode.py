"""Tests for choosing a KPI's tracking mode through the API (added with M10 slice F).

A KPI is "manual" (a person types in the actual value) or "task_count" (progress
is a live count of completed linked tasks). Before this, the API could only
create manual KPIs.
"""
import pytest

from tests.tasks.test_tasks_router import AUDIT, _world

KPIS = "/api/v1/kpis"


@pytest.mark.asyncio
async def test_a_kpi_can_be_created_as_task_count_and_defaults_to_manual(client, monkeypatch):
    """Choosing task_count on create is kept; leaving it out still gives manual."""
    w = await _world(client, monkeypatch, "km1")
    base = {"department_id": w.dispatch, "weight": 30, "target_value": 20}

    counted = await client.post(KPIS, json={**base, "name": "Close deals", "tracking_mode": "task_count"}, headers=w.hr)
    typed_in = await client.post(KPIS, json={**base, "name": "Revenue"}, headers=w.hr)

    assert counted.status_code in (200, 201) and counted.json()["tracking_mode"] == "task_count"
    assert typed_in.status_code in (200, 201) and typed_in.json()["tracking_mode"] == "manual"
    assert (await client.get(f"{KPIS}/{counted.json()['id']}", headers=w.hr)).json()["tracking_mode"] == "task_count"


@pytest.mark.asyncio
async def test_the_mode_can_be_changed_later_and_the_change_is_audited(client, monkeypatch):
    """From manual to task_count and back, each recorded with old and new values."""
    w = await _world(client, monkeypatch, "km2")
    kpi_id = (await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "Close deals", "weight": 50}, headers=w.hr
    )).json()["id"]

    to_counted = await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "task_count"}, headers=w.hr)
    back = await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "manual"}, headers=w.hr)
    other_edit = await client.patch(f"{KPIS}/{kpi_id}", json={"name": "Renamed"}, headers=w.hr)

    assert to_counted.json()["tracking_mode"] == "task_count"
    assert back.json()["tracking_mode"] == "manual"
    assert other_edit.json()["tracking_mode"] == "manual"          # an edit that leaves it out doesn't touch it
    audit = await client.get(AUDIT, params={"entity_type": "kpi", "entity_id": kpi_id}, headers=w.hr)
    changes = [e["changes"] for e in audit.json()["data"] if e["action"] == "update"]
    assert any(c["old"].get("tracking_mode") == "manual" and c["new"].get("tracking_mode") == "task_count" for c in changes)


@pytest.mark.asyncio
async def test_a_bad_mode_is_refused_and_an_employee_cannot_change_it(client, monkeypatch):
    """Unknown values are a 422; changing a KPI stays an HR-only action."""
    w = await _world(client, monkeypatch, "km3")
    kpi_id = (await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "Close deals", "weight": 50}, headers=w.hr
    )).json()["id"]

    bad_create = await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "X", "weight": 10, "tracking_mode": "vibes"}, headers=w.hr
    )
    bad_update = await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "vibes"}, headers=w.hr)
    by_employee = await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "task_count"}, headers=w.chidi.h)

    assert bad_create.status_code == 422 and bad_update.status_code == 422
    assert by_employee.status_code == 403
    assert (await client.get(f"{KPIS}/{kpi_id}", headers=w.hr)).json()["tracking_mode"] == "manual"


@pytest.mark.asyncio
async def test_an_explicit_null_mode_is_refused_and_does_not_break_the_kpi(client, monkeypatch):
    """Sending tracking_mode: null on update is a 422; the mode is never wiped (it is a required column)."""
    w = await _world(client, monkeypatch, "km4")
    kpi_id = (await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "Close deals", "weight": 50}, headers=w.hr
    )).json()["id"]

    resp = await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": None}, headers=w.hr)

    assert resp.status_code == 422
    assert (await client.get(f"{KPIS}/{kpi_id}", headers=w.hr)).json()["tracking_mode"] == "manual"
