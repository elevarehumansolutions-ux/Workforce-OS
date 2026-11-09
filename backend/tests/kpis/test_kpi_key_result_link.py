"""Linking a KPI to the key result it measures, through the API.

Scenario: Adaeze (HR) makes "On-time deliveries" measure the key result "95% on time". The link
must point at a real key result of her own company: not an invented id, not a deleted one, and
never another company's.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login
from tests.tasks.test_tasks_router import _auth_header, _world

KPIS = "/api/v1/kpis"
OKRS = "/api/v1/okrs"
KEY_RESULTS = "/api/v1/key-results"


async def _key_result(client, headers, description="95% of deliveries on time") -> str:
    okr = (await client.post(OKRS, json={"title": "Deliver on time"}, headers=headers)).json()
    kr = await client.post(f"{OKRS}/{okr['id']}/key-results", json={"description": description}, headers=headers)
    return kr.json()["id"]


@pytest.mark.asyncio
async def test_a_kpi_can_be_created_linked_to_a_key_result_of_the_company(client, monkeypatch):
    """The link is kept and comes back on the KPI."""
    w = await _world(client, monkeypatch, "kl1")
    key_result_id = await _key_result(client, w.hr)

    created = await client.post(
        KPIS,
        json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 50, "key_result_id": key_result_id},
        headers=w.hr,
    )

    assert created.status_code in (200, 201)
    assert created.json()["key_result_id"] == key_result_id


@pytest.mark.asyncio
async def test_an_invented_key_result_is_refused(client, monkeypatch):
    """A made-up id is a 404 with a clear code, not a database error."""
    w = await _world(client, monkeypatch, "kl2")

    created = await client.post(
        KPIS,
        json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 50, "key_result_id": str(uuid.uuid4())},
        headers=w.hr,
    )

    assert (created.status_code, created.json()["code"]) == (404, "KEY_RESULT_NOT_FOUND")
    assert (await client.get(f"{KPIS}?department_id={w.dispatch}", headers=w.hr)).json()["data"] == []


@pytest.mark.asyncio
async def test_another_companys_key_result_is_refused(client, monkeypatch):
    """Kelechi's key result id cannot be attached to Adaeze's KPI: tenant isolation."""
    w = await _world(client, monkeypatch, "kl3")
    other = await register_verified_and_login(client, email="kl3_other@example.com")
    foreign_key_result = await _key_result(client, _auth_header(other["access_token"]), "Their own result")

    created = await client.post(
        KPIS,
        json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 50, "key_result_id": foreign_key_result},
        headers=w.hr,
    )

    assert (created.status_code, created.json()["code"]) == (404, "KEY_RESULT_NOT_FOUND")


@pytest.mark.asyncio
async def test_a_link_can_be_added_changed_and_removed_later(client, monkeypatch):
    """PATCH sets it, moves it, and null clears it; leaving the field out keeps it."""
    w = await _world(client, monkeypatch, "kl4")
    first = await _key_result(client, w.hr, "First result")
    second = await _key_result(client, w.hr, "Second result")
    kpi_id = (await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 50}, headers=w.hr
    )).json()["id"]

    linked = await client.patch(f"{KPIS}/{kpi_id}", json={"key_result_id": first}, headers=w.hr)
    renamed = await client.patch(f"{KPIS}/{kpi_id}", json={"name": "Renamed"}, headers=w.hr)
    moved = await client.patch(f"{KPIS}/{kpi_id}", json={"key_result_id": second}, headers=w.hr)
    cleared = await client.patch(f"{KPIS}/{kpi_id}", json={"key_result_id": None}, headers=w.hr)

    assert linked.json()["key_result_id"] == first
    assert renamed.json()["key_result_id"] == first
    assert moved.json()["key_result_id"] == second
    assert cleared.json()["key_result_id"] is None


@pytest.mark.asyncio
async def test_updating_to_an_unknown_key_result_is_refused_and_changes_nothing(client, monkeypatch):
    """The KPI keeps its old link when the new one is invalid."""
    w = await _world(client, monkeypatch, "kl5")
    real = await _key_result(client, w.hr)
    kpi_id = (await client.post(
        KPIS,
        json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 50, "key_result_id": real},
        headers=w.hr,
    )).json()["id"]

    refused = await client.patch(f"{KPIS}/{kpi_id}", json={"key_result_id": str(uuid.uuid4())}, headers=w.hr)

    assert (refused.status_code, refused.json()["code"]) == (404, "KEY_RESULT_NOT_FOUND")
    assert (await client.get(f"{KPIS}/{kpi_id}", headers=w.hr)).json()["key_result_id"] == real


@pytest.mark.asyncio
async def test_a_deleted_key_result_cannot_be_linked(client, monkeypatch):
    """Deleting the key result first, then trying to link a KPI to it: refused."""
    w = await _world(client, monkeypatch, "kl6")
    key_result_id = await _key_result(client, w.hr)
    assert (await client.delete(f"{KEY_RESULTS}/{key_result_id}", headers=w.hr)).status_code in (200, 204)

    created = await client.post(
        KPIS,
        json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 50, "key_result_id": key_result_id},
        headers=w.hr,
    )

    assert (created.status_code, created.json()["code"]) == (404, "KEY_RESULT_NOT_FOUND")
