"""HTTP-level tests for /locations CRUD."""
import pytest

LOCATIONS = "/api/v1/locations"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _invite_and_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    from unittest.mock import MagicMock
    import app.modules.tenancy_identity.router as membership_router_module

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": email, "role": role},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Test Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return accept_resp.json()


@pytest.mark.asyncio
async def test_locations_require_authentication(client):
    resp = await client.get(LOCATIONS)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_location_requires_hr_admin_role(client, monkeypatch):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="loc_owner1@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "loc_emp1@example.com", "employee")

    resp = await client.post(
        LOCATIONS, json={"name": "HQ"}, headers=_auth_header(employee["access_token"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_any_role_can_read_locations(client, monkeypatch):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="loc_owner2@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "loc_emp2@example.com", "employee")

    await client.post(LOCATIONS, json={"name": "HQ"}, headers=_auth_header(owner["access_token"]))
    resp = await client.get(LOCATIONS, headers=_auth_header(employee["access_token"]))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_get_update_delete_location(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="loc_owner3@example.com")
    h = _auth_header(owner["access_token"])

    create_resp = await client.post(LOCATIONS, json={"name": "Lagos", "address": "1 Way St"}, headers=h)
    assert create_resp.status_code == 200
    location_id = create_resp.json()["id"]
    assert create_resp.json()["address"] == "1 Way St"

    get_resp = await client.get(f"{LOCATIONS}/{location_id}", headers=h)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Lagos"

    update_resp = await client.patch(f"{LOCATIONS}/{location_id}", json={"name": "Lagos HQ"}, headers=h)
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Lagos HQ"
    assert update_resp.json()["address"] == "1 Way St"  # untouched field survives a partial update

    delete_resp = await client.delete(f"{LOCATIONS}/{location_id}", headers=h)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted_at"] is not None

    get_after_delete = await client.get(f"{LOCATIONS}/{location_id}", headers=h)
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_list_locations_is_paginated_and_org_scoped(client):
    """RLS proof: an org only ever sees its own locations, even though
    both orgs' rows sit in the same table."""
    from tests.conftest import register_verified_and_login

    owner_a = await register_verified_and_login(client, email="loc_owner_a@example.com")
    owner_b = await register_verified_and_login(client, email="loc_owner_b@example.com")

    for name in ("Lagos", "Abuja", "Kano"):
        resp = await client.post(LOCATIONS, json={"name": name}, headers=_auth_header(owner_a["access_token"]))
        assert resp.status_code == 200
    await client.post(LOCATIONS, json={"name": "Nairobi"}, headers=_auth_header(owner_b["access_token"]))

    page1 = await client.get(LOCATIONS, params={"limit": 2}, headers=_auth_header(owner_a["access_token"]))
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["pagination"]["total"] == 3
    assert len(body1["data"]) == 2

    resp_b = await client.get(LOCATIONS, headers=_auth_header(owner_b["access_token"]))
    assert resp_b.json()["pagination"]["total"] == 1
    assert resp_b.json()["data"][0]["name"] == "Nairobi"
