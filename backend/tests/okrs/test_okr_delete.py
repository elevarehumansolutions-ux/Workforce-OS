"""HTTP-level tests for DELETE /okrs/{id} and DELETE /key-results/{id}.

Rule (08_DECISIONS.md 2026-11-05): soft delete, HR only, refused with 409
RESOURCE_IN_USE while a KPI still measures a key result.
"""
import pytest

from tests.okrs.test_okrs_router import _auth_header, _invite_and_accept

OKRS = "/api/v1/okrs"
KEY_RESULTS = "/api/v1/key-results"
KPIS = "/api/v1/kpis"
DEPARTMENTS = "/api/v1/departments"


async def _okr_with_key_result(client, headers):
    """Make one objective with one key result and return both ids."""
    okr = await client.post(OKRS, json={"title": "Grow revenue"}, headers=headers)
    okr_id = okr.json()["id"]
    kr = await client.post(
        f"{OKRS}/{okr_id}/key-results", json={"description": "Close 10 deals"}, headers=headers
    )
    return okr_id, kr.json()["id"]


async def _kpi_measuring(client, headers, key_result_id):
    """Make a department and a KPI that measures the given key result."""
    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)
    resp = await client.post(
        KPIS,
        json={
            "department_id": dept.json()["id"],
            "name": "Deals closed",
            "weight": 30,
            "key_result_id": key_result_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_delete_key_result_removes_it_from_the_list(client):
    """A deleted key result disappears from its objective, and a second delete is a 404."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="krdel_owner1@example.com")
    h = _auth_header(owner["access_token"])
    okr_id, kr_id = await _okr_with_key_result(client, h)

    resp = await client.delete(f"{KEY_RESULTS}/{kr_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is not None

    listed = await client.get(f"{OKRS}/{okr_id}/key-results", headers=h)
    assert listed.json()["pagination"]["total"] == 0
    assert (await client.delete(f"{KEY_RESULTS}/{kr_id}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_delete_key_result_is_refused_while_a_kpi_measures_it(client):
    """409 RESOURCE_IN_USE names the KPI count, and the key result stays."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="krdel_owner2@example.com")
    h = _auth_header(owner["access_token"])
    okr_id, kr_id = await _okr_with_key_result(client, h)
    await _kpi_measuring(client, h, kr_id)

    refused = await client.delete(f"{KEY_RESULTS}/{kr_id}", headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "RESOURCE_IN_USE"
    assert "1 KPI" in refused.json()["message"]

    listed = await client.get(f"{OKRS}/{okr_id}/key-results", headers=h)
    assert listed.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_delete_okr_removes_the_objective_and_its_key_results(client):
    """Deleting an objective with no KPIs on it takes its key results with it."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okrdel_owner1@example.com")
    h = _auth_header(owner["access_token"])
    okr_id, kr_id = await _okr_with_key_result(client, h)

    resp = await client.delete(f"{OKRS}/{okr_id}", headers=h)
    assert resp.status_code == 200

    assert (await client.get(f"{OKRS}/{okr_id}", headers=h)).status_code == 404
    assert (await client.patch(f"{KEY_RESULTS}/{kr_id}", json={"description": "x"}, headers=h)).status_code == 404
    listing = await client.get(OKRS, headers=h)
    assert listing.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_delete_okr_is_refused_while_a_kpi_measures_a_key_result(client):
    """409, and neither the objective nor its key results are touched."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okrdel_owner2@example.com")
    h = _auth_header(owner["access_token"])
    okr_id, kr_id = await _okr_with_key_result(client, h)
    await _kpi_measuring(client, h, kr_id)

    refused = await client.delete(f"{OKRS}/{okr_id}", headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "RESOURCE_IN_USE"

    assert (await client.get(f"{OKRS}/{okr_id}", headers=h)).status_code == 200
    listed = await client.get(f"{OKRS}/{okr_id}/key-results", headers=h)
    assert listed.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_delete_is_hr_only(client, monkeypatch):
    """A manager is refused with 403 on both deletes, and nothing is removed."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okrdel_owner3@example.com")
    manager = await _invite_and_accept(client, monkeypatch, owner, "okrdel_mgr3@example.com", "manager")
    h = _auth_header(owner["access_token"])
    okr_id, kr_id = await _okr_with_key_result(client, h)
    m = _auth_header(manager["access_token"])

    assert (await client.delete(f"{KEY_RESULTS}/{kr_id}", headers=m)).status_code == 403
    assert (await client.delete(f"{OKRS}/{okr_id}", headers=m)).status_code == 403
    assert (await client.get(f"{OKRS}/{okr_id}", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_another_organization_cannot_delete_it(client):
    """Org B gets 404 (not 403) for org A's objective and key result."""
    from tests.conftest import register_verified_and_login

    owner_a = await register_verified_and_login(client, email="okrdel_a@example.com")
    owner_b = await register_verified_and_login(client, email="okrdel_b@example.com")
    okr_id, kr_id = await _okr_with_key_result(client, _auth_header(owner_a["access_token"]))
    b = _auth_header(owner_b["access_token"])

    assert (await client.delete(f"{OKRS}/{okr_id}", headers=b)).status_code == 404
    assert (await client.delete(f"{KEY_RESULTS}/{kr_id}", headers=b)).status_code == 404
