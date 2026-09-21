"""HTTP-level tests for POST /employees/{id}/offboard and /reinstate."""
from datetime import date
from unittest.mock import MagicMock

import pytest

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _setup_position(client, h) -> str:
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "Engineer"}, headers=h)
    return pos.json()["id"]


async def _invite_via_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    """Accept-invite, not direct registration — a directly registered user
    always keeps their own founding org as an extra active membership,
    which would mask whether offboarding's deactivation actually blocks
    login (same reasoning as tests/memberships/test_memberships.py)."""
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
            "full_name": "Terry Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return accept_resp.json()


@pytest.mark.asyncio
async def test_offboard_deactivates_linked_membership_and_blocks_login(client, monkeypatch):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="off_owner1@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    teammate_email = "teammate1@example.com"
    teammate = await _invite_via_accept(client, monkeypatch, owner, teammate_email, "manager")

    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "user_id": teammate["user"]["id"],
            "first_name": "Terry",
            "last_name": "Teammate",
            "work_email": teammate_email,
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    employee_id = emp.json()["id"]

    login_before = await client.post(
        f"{AUTH}/login", json={"email": teammate_email, "password": "Password123#"}
    )
    assert login_before.status_code == 200

    offboard = await client.post(f"{EMPLOYEES}/{employee_id}/offboard", headers=h)
    assert offboard.status_code == 200
    assert offboard.json()["status"] == "inactive"

    login_after = await client.post(
        f"{AUTH}/login", json={"email": teammate_email, "password": "Password123#"}
    )
    assert login_after.status_code == 403
    assert login_after.json()["code"] == "NO_ACTIVE_MEMBERSHIP"


@pytest.mark.asyncio
async def test_offboard_employee_without_login_access_just_sets_status(client):
    """employees.user_id is nullable — someone can exist in the org
    structure without ever having login access. Offboarding them must not
    error just because there's no Membership to touch."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="off_owner2@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "No",
            "last_name": "Login",
            "work_email": "nologin@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    employee_id = emp.json()["id"]

    offboard = await client.post(f"{EMPLOYEES}/{employee_id}/offboard", headers=h)
    assert offboard.status_code == 200
    assert offboard.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_offboard_does_not_block_on_direct_reports(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="off_owner3@example.com")
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    manager_pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "Manager"}, headers=h
    )
    report_pos = await client.post(
        POSITIONS,
        json={
            "department_id": dept.json()["id"],
            "title": "Report",
            "reports_to_position_id": manager_pos.json()["id"],
        },
        headers=h,
    )

    manager_emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": manager_pos.json()["id"],
            "first_name": "Mia",
            "last_name": "Manager",
            "work_email": "mia@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    await client.post(
        EMPLOYEES,
        json={
            "position_id": report_pos.json()["id"],
            "manager_id": manager_emp.json()["id"],
            "first_name": "Rex",
            "last_name": "Report",
            "work_email": "rex@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )

    offboard = await client.post(f"{EMPLOYEES}/{manager_emp.json()['id']}/offboard", headers=h)
    assert offboard.status_code == 200
    assert offboard.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_offboard_twice_rejected(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="off_owner4@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "Once",
            "last_name": "Only",
            "work_email": "once@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    employee_id = emp.json()["id"]

    first = await client.post(f"{EMPLOYEES}/{employee_id}/offboard", headers=h)
    assert first.status_code == 200

    second = await client.post(f"{EMPLOYEES}/{employee_id}/offboard", headers=h)
    assert second.status_code == 422


@pytest.mark.asyncio
async def test_reinstate_restores_status_and_login(client, monkeypatch):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="off_owner5@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    teammate_email = "teammate5@example.com"
    teammate = await _invite_via_accept(client, monkeypatch, owner, teammate_email, "employee")

    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "user_id": teammate["user"]["id"],
            "first_name": "Terry",
            "last_name": "Teammate",
            "work_email": teammate_email,
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    employee_id = emp.json()["id"]

    await client.post(f"{EMPLOYEES}/{employee_id}/offboard", headers=h)
    blocked_login = await client.post(
        f"{AUTH}/login", json={"email": teammate_email, "password": "Password123#"}
    )
    assert blocked_login.status_code == 403

    reinstate = await client.post(f"{EMPLOYEES}/{employee_id}/reinstate", headers=h)
    assert reinstate.status_code == 200
    assert reinstate.json()["status"] == "active"

    restored_login = await client.post(
        f"{AUTH}/login", json={"email": teammate_email, "password": "Password123#"}
    )
    assert restored_login.status_code == 200


@pytest.mark.asyncio
async def test_reinstate_active_employee_rejected(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="off_owner6@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "Still",
            "last_name": "Active",
            "work_email": "active@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )

    resp = await client.post(f"{EMPLOYEES}/{emp.json()['id']}/reinstate", headers=h)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_offboard_endpoint_requires_hr_admin_role(client, monkeypatch):
    from tests.conftest import register_verified_and_login
    from unittest.mock import MagicMock
    import app.modules.tenancy_identity.router as membership_router_module

    owner = await register_verified_and_login(client, email="off_owner7@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": "Target",
            "last_name": "Employee",
            "work_email": "target@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)
    await client.post(
        MEMBERSHIPS, json={"email": "mgr7@example.com", "role": "manager"}, headers=h
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    manager_accept = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Manager Person",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )

    resp = await client.post(
        f"{EMPLOYEES}/{emp.json()['id']}/offboard",
        headers=_auth_header(manager_accept.json()["access_token"]),
    )
    assert resp.status_code == 403
