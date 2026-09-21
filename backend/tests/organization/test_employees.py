"""HTTP-level tests for /employees CRUD (offboard/reinstate covered
separately in test_employee_offboard_reinstate.py)."""
from datetime import date

import pytest

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
LOCATIONS = "/api/v1/locations"
EMPLOYEES = "/api/v1/employees"
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


async def _setup_position(client, h) -> str:
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "Engineer"}, headers=h)
    return pos.json()["id"]


@pytest.mark.asyncio
async def test_create_employee_requires_hr_admin_role(client, monkeypatch):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="emp_owner1@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    manager = await _invite_and_accept(client, monkeypatch, owner, "emp_mgr1@example.com", "manager")

    resp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "New",
            "last_name": "Hire",
            "work_email": "newhire@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=_auth_header(manager["access_token"]),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_employee_defaults_status_active_and_location_nullable(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="emp_owner2@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    resp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "Jane",
            "last_name": "Doe",
            "work_email": "jane@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["location_id"] is None
    assert body["user_id"] is None


@pytest.mark.asyncio
async def test_list_employees_filters_by_location(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="emp_owner3@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    loc_a = await client.post(LOCATIONS, json={"name": "Lagos"}, headers=h)
    loc_b = await client.post(LOCATIONS, json={"name": "Abuja"}, headers=h)

    await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "location_id": loc_a.json()["id"],
            "first_name": "A",
            "last_name": "Worker",
            "work_email": "a@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "location_id": loc_b.json()["id"],
            "first_name": "B",
            "last_name": "Worker",
            "work_email": "b@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )

    resp = await client.get(EMPLOYEES, params={"location_id": loc_a.json()["id"]}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1
    assert resp.json()["data"][0]["first_name"] == "A"


@pytest.mark.asyncio
async def test_update_employee_cannot_change_status(client):
    """PATCH /employees/{id} silently drops `status` (not a declared field
    on EmployeeUpdateRequest) — only offboard/reinstate can change it."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="emp_owner4@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    create_resp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "Sam",
            "last_name": "Worker",
            "work_email": "sam@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    employee_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"{EMPLOYEES}/{employee_id}",
        json={"phone_number": "555-0100", "status": "inactive"},
        headers=h,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["phone_number"] == "555-0100"
    assert update_resp.json()["status"] == "active"
