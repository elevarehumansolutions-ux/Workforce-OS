"""A workflow step can name the KPI its tasks count toward (08_DECISIONS.md 2026-11-14, to-do 46).

Scenario: the "Dispatch the goods" step counts toward Dispatch's "On-time deliveries" KPI. Every case
started from the template then creates a task already linked to that KPI, so it counts in scores
instead of showing "Linked KPI: None".
"""
import pytest
from sqlalchemy import text

from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import KPIS, _world
from tests.workflow.test_instance_start import _start, _tasks_of
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_list import _create

STEPS = "/api/v1/workflow-steps"


async def _kpi(client, w, department_id: str, name: str = "On-time deliveries") -> str:
    resp = await client.post(KPIS, json={"department_id": department_id, "name": name, "weight": 100}, headers=w.hr)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_a_step_with_a_kpi_creates_tasks_linked_to_it(client, monkeypatch):
    w = await _world(client, monkeypatch, "sk1")
    kpi_id = await _kpi(client, w, w.dispatch)
    template = await _create(client, w.hr, "Delivery", w.dispatch)
    added = await _add(client, w.hr, template["id"], "Dispatch the goods", w.dispatch, kpi_id=kpi_id)
    assert added.status_code == 200 and added.json()["kpi_id"] == kpi_id

    started = await _start(client, w.hr, template["id"])

    tasks = await _tasks_of(client, w, started.json()["id"])
    assert [t["kpi_id"] for t in tasks] == [kpi_id]


@pytest.mark.asyncio
async def test_a_step_without_a_kpi_creates_unlinked_tasks_as_before(client, monkeypatch):
    w = await _world(client, monkeypatch, "sk2")
    template = await _create(client, w.hr, "Delivery", w.dispatch)
    added = await _add(client, w.hr, template["id"], "Dispatch the goods", w.dispatch)
    assert added.json()["kpi_id"] is None

    started = await _start(client, w.hr, template["id"])

    assert [t["kpi_id"] for t in await _tasks_of(client, w, started.json()["id"])] == [None]


@pytest.mark.asyncio
async def test_a_kpi_of_another_department_is_refused(client, monkeypatch):
    """Scoring only counts a task whose KPI is the person's department's, so it would count for nothing."""
    w = await _world(client, monkeypatch, "sk3")
    sales_kpi = await _kpi(client, w, w.sales, "Deals closed")
    template = await _create(client, w.hr, "Delivery", w.dispatch)

    resp = await _add(client, w.hr, template["id"], "Dispatch the goods", w.dispatch, kpi_id=sales_kpi)

    assert resp.status_code == 422
    assert "another department" in resp.json()["message"]


@pytest.mark.asyncio
async def test_an_unknown_kpi_is_not_found(client, monkeypatch):
    w = await _world(client, monkeypatch, "sk4")
    template = await _create(client, w.hr, "Delivery", w.dispatch)

    resp = await _add(
        client, w.hr, template["id"], "Dispatch the goods", w.dispatch,
        kpi_id="00000000-0000-4000-8000-000000000000",
    )

    assert resp.status_code == 404 and resp.json()["code"] == "KPI_NOT_FOUND"


@pytest.mark.asyncio
async def test_editing_the_kpi_sets_it_and_null_removes_it(client, monkeypatch):
    w = await _world(client, monkeypatch, "sk5")
    kpi_id = await _kpi(client, w, w.dispatch)
    template = await _create(client, w.hr, "Delivery", w.dispatch)
    step = (await _add(client, w.hr, template["id"], "Dispatch the goods", w.dispatch)).json()

    set_it = await client.patch(f"{STEPS}/{step['id']}", json={"kpi_id": kpi_id}, headers=w.hr)
    removed = await client.patch(f"{STEPS}/{step['id']}", json={"kpi_id": None}, headers=w.hr)

    assert set_it.status_code == 200 and set_it.json()["kpi_id"] == kpi_id
    assert removed.status_code == 200 and removed.json()["kpi_id"] is None


@pytest.mark.asyncio
async def test_moving_a_step_to_another_department_drops_the_old_kpi(client, monkeypatch):
    w = await _world(client, monkeypatch, "sk6")
    kpi_id = await _kpi(client, w, w.dispatch)
    template = await _create(client, w.hr, "Delivery", w.dispatch)
    step = (await _add(client, w.hr, template["id"], "Hand-off", w.dispatch, kpi_id=kpi_id)).json()

    moved = await client.patch(f"{STEPS}/{step['id']}", json={"department_id": w.sales}, headers=w.hr)

    assert moved.status_code == 200
    assert moved.json()["department_id"] == w.sales and moved.json()["kpi_id"] is None


@pytest.mark.asyncio
async def test_moving_a_step_with_a_kpi_of_the_new_department_keeps_that_kpi(client, monkeypatch):
    w = await _world(client, monkeypatch, "sk7")
    sales_kpi = await _kpi(client, w, w.sales, "Deals closed")
    template = await _create(client, w.hr, "Delivery", w.dispatch)
    step = (await _add(client, w.hr, template["id"], "Hand-off", w.dispatch)).json()

    moved = await client.patch(
        f"{STEPS}/{step['id']}", json={"department_id": w.sales, "kpi_id": sales_kpi}, headers=w.hr
    )

    assert moved.status_code == 200 and moved.json()["kpi_id"] == sales_kpi


@pytest.mark.asyncio
async def test_a_kpi_deleted_after_the_step_was_set_up_does_not_stop_the_chain(client, db_session, monkeypatch):
    """The case still starts; the task is simply created without the KPI."""
    w = await _world(client, monkeypatch, "sk8")
    kpi_id = await _kpi(client, w, w.dispatch)
    template = await _create(client, w.hr, "Delivery", w.dispatch)
    await _add(client, w.hr, template["id"], "Dispatch the goods", w.dispatch, kpi_id=kpi_id)
    # There is no API to delete a KPI yet, so it is soft-deleted directly, as a later feature would.
    me = (await client.get("/api/v1/auth/me", headers=w.hr)).json()
    await set_org_context(db_session, me["memberships"][0]["organization"]["id"])
    await db_session.execute(text("UPDATE kpis SET deleted_at = now() WHERE id = :id"), {"id": kpi_id})

    started = await _start(client, w.hr, template["id"])

    assert started.status_code == 200
    assert [t["kpi_id"] for t in await _tasks_of(client, w, started.json()["id"])] == [None]
