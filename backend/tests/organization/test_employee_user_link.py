"""HTTP-level tests for linking a login (user) to an employee.

Covers the validation on ``POST /employees`` when ``user_id`` is given and
the dedicated ``POST /employees/{id}/link-user`` action: the user must be an
active member of the org, can be linked to at most one employee, and a
linked login is never cleared or swapped (08_DECISIONS.md 2026-10-01).
"""
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
    """Create a teammate via accept-invite so they hold exactly one membership."""
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


def _employee_body(position_id: str, email: str, user_id: str | None = None) -> dict:
    body = {
        "position_id": position_id,
        "first_name": "Test",
        "last_name": "Person",
        "work_email": email,
        "start_date": date.today().isoformat(),
    }
    if user_id is not None:
        body["user_id"] = user_id
    return body


@pytest.mark.asyncio
async def test_create_employee_can_link_an_org_member(client, monkeypatch):
    """Creating an employee with a member's user_id links them."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner1@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm1@example.com", "manager")

    resp = await client.post(
        EMPLOYEES, json=_employee_body(position_id, "link_tm1@example.com", teammate["user"]["id"]), headers=h
    )

    assert resp.status_code == 200
    assert resp.json()["user_id"] == teammate["user"]["id"]


@pytest.mark.asyncio
async def test_user_cannot_be_linked_to_two_employees(client, monkeypatch):
    """A second employee for an already-linked user is a 409 with a named code."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner2@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm2@example.com", "manager")
    user_id = teammate["user"]["id"]
    first = await client.post(EMPLOYEES, json=_employee_body(position_id, "a@example.com", user_id), headers=h)
    assert first.status_code == 200

    second = await client.post(EMPLOYEES, json=_employee_body(position_id, "b@example.com", user_id), headers=h)

    assert second.status_code == 409
    assert second.json()["code"] == "EMPLOYEE_USER_ALREADY_LINKED"


@pytest.mark.asyncio
async def test_cannot_link_a_user_from_another_organization(client):
    """A user with no membership in this org gets a 404, same as a user that doesn't exist."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner3@example.com")
    outsider = await register_verified_and_login(client, email="link_outsider3@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)

    resp = await client.post(
        EMPLOYEES, json=_employee_body(position_id, "x@example.com", outsider["user"]["id"]), headers=h
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_cannot_link_a_user_whose_membership_is_deactivated(client, monkeypatch):
    """An offboarded member (deactivated membership) must be reinstated, not re-linked."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner4@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm4@example.com", "manager")
    user_id = teammate["user"]["id"]
    emp = await client.post(EMPLOYEES, json=_employee_body(position_id, "link_tm4@example.com", user_id), headers=h)
    assert (await client.post(f"{EMPLOYEES}/{emp.json()['id']}/offboard", headers=h)).status_code == 200

    resp = await client.post(EMPLOYEES, json=_employee_body(position_id, "y@example.com", user_id), headers=h)

    assert resp.status_code == 409
    assert resp.json()["code"] == "MEMBERSHIP_DEACTIVATED"


@pytest.mark.asyncio
async def test_link_user_attaches_a_login_to_an_existing_employee(client, monkeypatch):
    """An employee created without a login can be linked to a member later."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner5@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm5@example.com", "employee")
    emp = await client.post(EMPLOYEES, json=_employee_body(position_id, "link_tm5@example.com"), headers=h)
    assert emp.json()["user_id"] is None

    resp = await client.post(
        f"{EMPLOYEES}/{emp.json()['id']}/link-user", json={"user_id": teammate["user"]["id"]}, headers=h
    )

    assert resp.status_code == 200
    assert resp.json()["user_id"] == teammate["user"]["id"]
    fetched = await client.get(f"{EMPLOYEES}/{emp.json()['id']}", headers=h)
    assert fetched.json()["user_id"] == teammate["user"]["id"]


@pytest.mark.asyncio
async def test_link_user_is_one_way(client, monkeypatch):
    """An employee that already has a login can't be re-linked, to the same or another user."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner6@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm6@example.com", "employee")
    emp = await client.post(
        EMPLOYEES, json=_employee_body(position_id, "link_tm6@example.com", teammate["user"]["id"]), headers=h
    )

    resp = await client.post(
        f"{EMPLOYEES}/{emp.json()['id']}/link-user", json={"user_id": owner["user"]["id"]}, headers=h
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "EMPLOYEE_ALREADY_HAS_LOGIN"


@pytest.mark.asyncio
async def test_link_user_rejects_a_user_already_linked_elsewhere(client, monkeypatch):
    """link-user runs the same already-linked check as create."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner7@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm7@example.com", "employee")
    user_id = teammate["user"]["id"]
    await client.post(EMPLOYEES, json=_employee_body(position_id, "link_tm7@example.com", user_id), headers=h)
    other = await client.post(EMPLOYEES, json=_employee_body(position_id, "other7@example.com"), headers=h)

    resp = await client.post(f"{EMPLOYEES}/{other.json()['id']}/link-user", json={"user_id": user_id}, headers=h)

    assert resp.status_code == 409
    assert resp.json()["code"] == "EMPLOYEE_USER_ALREADY_LINKED"


@pytest.mark.asyncio
async def test_link_user_requires_hr_admin_role(client, monkeypatch):
    """A manager can't link logins."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner8@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    manager = await _invite_via_accept(client, monkeypatch, owner, "link_mgr8@example.com", "manager")
    emp = await client.post(EMPLOYEES, json=_employee_body(position_id, "someone8@example.com"), headers=h)

    resp = await client.post(
        f"{EMPLOYEES}/{emp.json()['id']}/link-user",
        json={"user_id": manager["user"]["id"]},
        headers=_auth_header(manager["access_token"]),
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_link_user_unknown_employee_is_404(client):
    """Linking to an employee id that doesn't exist is a 404."""
    import uuid

    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner9@example.com")
    h = _auth_header(owner["access_token"])

    resp = await client.post(
        f"{EMPLOYEES}/{uuid.uuid4()}/link-user", json={"user_id": owner["user"]["id"]}, headers=h
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_link_user_writes_an_audit_entry(client, monkeypatch):
    """The link is audit-logged as its own action, not a generic update."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="link_owner10@example.com")
    h = _auth_header(owner["access_token"])
    position_id = await _setup_position(client, h)
    teammate = await _invite_via_accept(client, monkeypatch, owner, "link_tm10@example.com", "employee")
    emp = await client.post(EMPLOYEES, json=_employee_body(position_id, "link_tm10@example.com"), headers=h)
    await client.post(
        f"{EMPLOYEES}/{emp.json()['id']}/link-user", json={"user_id": teammate["user"]["id"]}, headers=h
    )

    audit = await client.get(
        "/api/v1/audit-log", params={"entity_type": "employee", "entity_id": emp.json()["id"]}, headers=h
    )

    assert audit.status_code == 200
    assert "link_user" in {entry["action"] for entry in audit.json()["data"]}
