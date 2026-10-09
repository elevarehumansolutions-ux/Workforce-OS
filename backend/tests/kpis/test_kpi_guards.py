"""Tests for two guards on KPIs (added with M10 slice F).

1. A KPI counted from completed tasks (tracking_mode task_count) refuses
   typed-in values, so there is only ever one source of truth for it.
2. PATCH /kpis/{id} refuses an explicit null on the fields every KPI must have
   (a clean 422, not a database crash), while leaving a field out still means
   "keep it" and genuinely optional fields can still be cleared.
"""
from datetime import date, timedelta

import pytest

from tests.tasks.test_tasks_router import _world

KPIS = "/api/v1/kpis"


async def _kpi(client, w, **fields) -> str:
    body = {"department_id": w.dispatch, "name": "Close deals", "weight": 50, "target_value": 20, **fields}
    resp = await client.post(KPIS, json=body, headers=w.hr)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _this_quarter_score(actual):
    """A typed-in score for a period that is still open."""
    return {
        "period_start": date.today().isoformat(),
        "period_end": (date.today() + timedelta(days=30)).isoformat(),
        "actual_value": actual,
    }


@pytest.mark.asyncio
async def test_a_typed_value_is_refused_for_a_task_count_kpi_and_allowed_again_when_manual(client, monkeypatch):
    """12 typed in for a counted KPI is a 409 and nothing is stored; switch it to manual and it works."""
    w = await _world(client, monkeypatch, "kg1")
    kpi_id = await _kpi(client, w, tracking_mode="task_count")

    refused = await client.post(f"{KPIS}/{kpi_id}/scores", json=_this_quarter_score(12), headers=w.hr)
    stored_after_refusal = await client.get(f"{KPIS}/{kpi_id}/scores", headers=w.hr)
    await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "manual"}, headers=w.hr)
    allowed = await client.post(f"{KPIS}/{kpi_id}/scores", json=_this_quarter_score(12), headers=w.hr)
    await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "task_count"}, headers=w.hr)
    refused_again = await client.post(f"{KPIS}/{kpi_id}/scores", json=_this_quarter_score(15), headers=w.hr)

    assert refused.status_code == 409 and refused.json()["code"] == "KPI_TRACKED_BY_TASKS"
    assert "counted from completed tasks" in refused.json()["message"]
    assert stored_after_refusal.json()["data"] == []
    assert allowed.status_code == 200 and float(allowed.json()["score_percentage"]) == 60
    assert refused_again.status_code == 409


@pytest.mark.asyncio
async def test_a_manual_kpi_still_takes_typed_values(client, monkeypatch):
    """The ordinary case is untouched."""
    w = await _world(client, monkeypatch, "kg2")
    kpi_id = await _kpi(client, w)

    resp = await client.post(f"{KPIS}/{kpi_id}/scores", json=_this_quarter_score(10), headers=w.hr)

    assert resp.status_code == 200 and float(resp.json()["score_percentage"]) == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["name", "weight", "is_inverse", "tracking_mode"])
async def test_an_explicit_null_on_a_required_field_is_a_422_and_changes_nothing(client, monkeypatch, field):
    """Each required field: null is refused cleanly and the KPI is exactly as it was."""
    w = await _world(client, monkeypatch, f"kg3{field[:2]}")
    kpi_id = await _kpi(client, w)
    before = (await client.get(f"{KPIS}/{kpi_id}", headers=w.hr)).json()

    resp = await client.patch(f"{KPIS}/{kpi_id}", json={field: None}, headers=w.hr)

    assert resp.status_code == 422
    assert (await client.get(f"{KPIS}/{kpi_id}", headers=w.hr)).json() == before


@pytest.mark.asyncio
async def test_leaving_fields_out_and_clearing_optional_ones_still_work(client, monkeypatch):
    """Omitting a field keeps it; description, target and unit may genuinely be cleared with null."""
    w = await _world(client, monkeypatch, "kg4")
    kpi_id = await _kpi(client, w, description="Deals closed", unit="deals")

    renamed = await client.patch(f"{KPIS}/{kpi_id}", json={"name": "Won deals"}, headers=w.hr)
    cleared = await client.patch(
        f"{KPIS}/{kpi_id}", json={"description": None, "target_value": None, "unit": None}, headers=w.hr
    )

    assert renamed.status_code == 200 and renamed.json()["name"] == "Won deals"
    assert renamed.json()["weight"] is not None and renamed.json()["is_inverse"] is False   # untouched
    assert cleared.status_code == 200
    assert (cleared.json()["description"], cleared.json()["target_value"], cleared.json()["unit"]) == (None, None, None)
    assert cleared.json()["name"] == "Won deals"
