"""Tests for the live task count of a task-count KPI (M10 slice F).

A KPI is switched to task_count through the real API (PATCH /kpis/{id}), so
these tests prove the whole path: create the KPI, switch its mode, complete
linked tasks, read the progress.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.tasks.periods import current_fiscal_quarter
from tests.conftest import register_verified_and_login
from tests.tasks.test_tasks_router import TASKS, _task, _world

KPIS = "/api/v1/kpis"


async def _kpi(client, w, name, weight, target=None, unit=None) -> str:
    """Create a Dispatch KPI as HR."""
    body = {"department_id": w.dispatch, "name": name, "weight": weight}
    if target is not None:
        body["target_value"] = target
    if unit is not None:
        body["unit"] = unit
    resp = await client.post(KPIS, json=body, headers=w.hr)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _make_task_count(client, w, kpi_id) -> None:
    """Switch a KPI to count tasks, as HR would."""
    resp = await client.patch(f"{KPIS}/{kpi_id}", json={"tracking_mode": "task_count"}, headers=w.hr)
    assert resp.status_code == 200 and resp.json()["tracking_mode"] == "task_count"


async def _completed_task(client, w, title, kpi_id) -> str:
    tid = (await _task(client, w.hr, w.dispatch, title, kpi_id=kpi_id)).json()["id"]
    await client.post(f"{TASKS}/{tid}/complete", headers=w.hr)
    return tid


@pytest.mark.asyncio
async def test_only_completed_linked_tasks_in_this_quarter_are_counted(client, monkeypatch, db_session):
    """3 deals closed this quarter of a target of 20: 3 tasks, 15%. Open, cancelled, other-KPI and old ones don't count."""
    w = await _world(client, monkeypatch, "f1")
    deals = await _kpi(client, w, "Close deals", 50, target=20, unit="deals")
    other = await _kpi(client, w, "Other KPI", 50, target=10)
    await _make_task_count(client, w, deals)
    for title in ("Deal 1", "Deal 2", "Deal 3"):
        await _completed_task(client, w, title, deals)
    old_one = await _completed_task(client, w, "Last year's deal", deals)
    await _completed_task(client, w, "Someone else's", other)
    await _task(client, w.hr, w.dispatch, "Still open", kpi_id=deals)
    cancelled = (await _task(client, w.hr, w.dispatch, "Dropped", kpi_id=deals)).json()["id"]
    await client.post(f"{TASKS}/{cancelled}/cancel", json={"reason": "Not needed"}, headers=w.hr)
    await db_session.execute(
        text("UPDATE tasks SET completed_at = '2020-01-15T10:00:00+00:00' WHERE id = :id"), {"id": old_one}
    )

    resp = await client.get(f"{KPIS}/{deals}/task-progress", headers=w.hr)

    assert resp.status_code == 200
    body = resp.json()
    assert body["kpi_id"] == deals and body["completed_tasks"] == 3 and body["unit"] == "deals"
    assert float(body["target_value"]) == 20 and float(body["score_percentage"]) == 15


@pytest.mark.asyncio
async def test_the_period_is_the_organizations_current_fiscal_quarter(client, monkeypatch, db_session):
    """period_start and period_end are the first and last day of the quarter containing today."""
    w = await _world(client, monkeypatch, "f2")
    kpi_id = await _kpi(client, w, "Close deals", 100, target=20)
    await _make_task_count(client, w, kpi_id)
    org = (await db_session.execute(
        text("SELECT fiscal_year_start_month, timezone FROM organizations WHERE id = :id"),
        {"id": w.owner["organization"]["id"]},
    )).one()
    start, end = current_fiscal_quarter(org.fiscal_year_start_month, org.timezone, datetime.now(UTC))

    body = (await client.get(f"{KPIS}/{kpi_id}/task-progress", headers=w.hr)).json()

    assert body["period_start"] == start.date().isoformat()
    assert body["period_end"] == (end - timedelta(days=1)).date().isoformat()


@pytest.mark.asyncio
async def test_no_target_means_no_percentage_and_zero_tasks_is_zero(client, monkeypatch, db_session):
    """Without a target the percentage is null (as for typed-in values); with no completed tasks the count is 0."""
    w = await _world(client, monkeypatch, "f3")
    no_target = await _kpi(client, w, "No target set", 50)
    nothing_yet = await _kpi(client, w, "Nothing yet", 50, target=10)
    for kpi_id in (no_target, nothing_yet):
        await _make_task_count(client, w, kpi_id)
    await _completed_task(client, w, "One", no_target)

    a = (await client.get(f"{KPIS}/{no_target}/task-progress", headers=w.hr)).json()
    b = (await client.get(f"{KPIS}/{nothing_yet}/task-progress", headers=w.hr)).json()

    assert a["completed_tasks"] == 1 and a["score_percentage"] is None and a["target_value"] is None
    assert b["completed_tasks"] == 0 and float(b["score_percentage"]) == 0


@pytest.mark.asyncio
async def test_who_can_read_it_and_what_is_refused(client, monkeypatch, db_session):
    """Any member can read it; a typed-in KPI is a 422; an unknown KPI or another organization is a 404."""
    w = await _world(client, monkeypatch, "f4")
    counted = await _kpi(client, w, "Counted", 50, target=5)
    typed_in = await _kpi(client, w, "Typed in", 50, target=5)       # stays manual
    await _make_task_count(client, w, counted)
    other_org = await register_verified_and_login(client, email="tk_other_f4@example.com")
    other_h = {"Authorization": f"Bearer {other_org['access_token']}"}

    as_employee = await client.get(f"{KPIS}/{counted}/task-progress", headers=w.chidi.h)
    manual = await client.get(f"{KPIS}/{typed_in}/task-progress", headers=w.hr)
    unknown = await client.get(f"{KPIS}/{'0' * 8}-0000-0000-0000-{'0' * 12}/task-progress", headers=w.hr)
    foreign = await client.get(f"{KPIS}/{counted}/task-progress", headers=other_h)

    assert as_employee.status_code == 200
    assert manual.status_code == 422 and "counting tasks" in manual.json()["message"]
    assert unknown.status_code == 404 and unknown.json()["code"] == "KPI_NOT_FOUND"
    assert foreign.status_code == 404
