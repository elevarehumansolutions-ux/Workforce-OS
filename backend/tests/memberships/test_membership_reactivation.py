"""HTTP-level tests for POST /memberships/{id}/reactivate.

Reactivation is its own action: an invite never restores a deactivated
member (tests/memberships/test_memberships.py), and the endpoint refuses
people whose employee record is offboarded, so login access and employment
status never disagree (08_DECISIONS.md 2026-10-02).
"""
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from tests.conftest import register_verified_and_login

AUTH = "/api/v1/auth"
MEMBERSHIPS = "/api/v1/memberships"
EMPLOYEES = "/api/v1/employees"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _teammate(client, monkeypatch, owner, email: str, role: str = "employee") -> dict:
    """Invite and accept a teammate; returns the accept-invite body."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(
        MEMBERSHIPS, json={"email": email, "role": role}, headers=_auth_header(owner["access_token"])
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Test Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return resp.json()


async def _deactivate(client, owner, membership_id: str) -> None:
    resp = await client.patch(
        f"{MEMBERSHIPS}/{membership_id}",
        json={"is_deactivated": True},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_reactivate_keeps_the_previous_role_when_none_is_given(client, monkeypatch):
    """Without a body the person comes back with the role they had."""
    owner = await register_verified_and_login(client, email="react_owner1@example.com")
    tm = await _teammate(client, monkeypatch, owner, "react_tm1@example.com", role="manager")
    membership_id = tm["membership"]["id"]
    await _deactivate(client, owner, membership_id)

    resp = await client.post(
        f"{MEMBERSHIPS}/{membership_id}/reactivate", headers=_auth_header(owner["access_token"])
    )

    assert resp.status_code == 200
    assert resp.json()["deactivated_at"] is None
    assert resp.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_patch_no_longer_reactivates(client, monkeypatch):
    """PATCH is_deactivated:false is a 422 pointing at /reactivate, and changes nothing."""
    owner = await register_verified_and_login(client, email="react_owner0@example.com")
    tm = await _teammate(client, monkeypatch, owner, "react_tm0@example.com")
    membership_id = tm["membership"]["id"]
    await _deactivate(client, owner, membership_id)

    resp = await client.patch(
        f"{MEMBERSHIPS}/{membership_id}",
        json={"is_deactivated": False},
        headers=_auth_header(owner["access_token"]),
    )

    assert resp.status_code == 422
    assert "reactivate" in resp.text
    login = await client.post(
        f"{AUTH}/login", json={"email": "react_tm0@example.com", "password": "Password123#"}
    )
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_reactivating_an_active_membership_is_a_conflict(client, monkeypatch):
    """Only a deactivated membership can be reactivated."""
    owner = await register_verified_and_login(client, email="react_owner2@example.com")
    tm = await _teammate(client, monkeypatch, owner, "react_tm2@example.com")

    resp = await client.post(
        f"{MEMBERSHIPS}/{tm['membership']['id']}/reactivate", headers=_auth_header(owner["access_token"])
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "MEMBERSHIP_NOT_DEACTIVATED"


@pytest.mark.asyncio
async def test_reactivate_is_refused_for_an_offboarded_employee(client, monkeypatch):
    """Offboarded people come back through the employee reinstate action, which keeps both in step."""
    owner = await register_verified_and_login(client, email="react_owner3@example.com")
    h = _auth_header(owner["access_token"])
    tm = await _teammate(client, monkeypatch, owner, "react_tm3@example.com")
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        "/api/v1/positions", json={"department_id": dept.json()["id"], "title": "Engineer"}, headers=h
    )
    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": pos.json()["id"],
            "user_id": tm["user"]["id"],
            "first_name": "Test",
            "last_name": "Teammate",
            "work_email": "react_tm3@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )
    assert (await client.post(f"{EMPLOYEES}/{emp.json()['id']}/offboard", headers=h)).status_code == 200

    resp = await client.post(f"{MEMBERSHIPS}/{tm['membership']['id']}/reactivate", headers=h)

    assert resp.status_code == 422
    assert "reinstate" in resp.json()["message"].lower()
    reinstated = await client.post(f"{EMPLOYEES}/{emp.json()['id']}/reinstate", headers=h)
    assert reinstated.status_code == 200
    login = await client.post(
        f"{AUTH}/login", json={"email": "react_tm3@example.com", "password": "Password123#"}
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_reactivate_requires_hr_admin_and_stays_inside_the_org(client, monkeypatch):
    """A manager gets 403; another org's admin and an unknown id get 404."""
    owner = await register_verified_and_login(client, email="react_owner4@example.com")
    outsider = await register_verified_and_login(client, email="react_outsider4@example.com")
    manager = await _teammate(client, monkeypatch, owner, "react_mgr4@example.com", role="manager")
    tm = await _teammate(client, monkeypatch, owner, "react_tm4@example.com")
    await _deactivate(client, owner, tm["membership"]["id"])
    target = f"{MEMBERSHIPS}/{tm['membership']['id']}/reactivate"

    as_manager = await client.post(target, headers=_auth_header(manager["access_token"]))
    as_outsider = await client.post(target, headers=_auth_header(outsider["access_token"]))
    unknown = await client.post(
        f"{MEMBERSHIPS}/{uuid.uuid4()}/reactivate", headers=_auth_header(owner["access_token"])
    )

    assert as_manager.status_code == 403
    assert as_outsider.status_code == 404
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_reactivation_is_audit_logged(client, monkeypatch):
    """Restoring someone's access leaves an audit entry with the old and new state."""
    owner = await register_verified_and_login(client, email="react_owner5@example.com")
    h = _auth_header(owner["access_token"])
    tm = await _teammate(client, monkeypatch, owner, "react_tm5@example.com")
    membership_id = tm["membership"]["id"]
    await _deactivate(client, owner, membership_id)
    await client.post(f"{MEMBERSHIPS}/{membership_id}/reactivate", headers=h)

    audit = await client.get(
        "/api/v1/audit-log", params={"entity_type": "membership", "entity_id": membership_id}, headers=h
    )

    entries = [e for e in audit.json()["data"] if e["action"] == "reactivate"]
    assert len(entries) == 1
    assert entries[0]["changes"]["new"]["deactivated_at"] is None
    assert entries[0]["changes"]["old"]["deactivated_at"] is not None


@pytest.mark.asyncio
async def test_grant_login_for_a_deactivated_member_is_refused(client, monkeypatch):
    """Send invite on an employee whose email belongs to a deactivated member points to reactivation."""
    import app.modules.organization.router as employee_router

    monkeypatch.setattr(employee_router, "dispatch_invite_email", MagicMock())
    owner = await register_verified_and_login(client, email="react_owner6@example.com")
    h = _auth_header(owner["access_token"])
    tm = await _teammate(client, monkeypatch, owner, "react_tm6@example.com")
    await _deactivate(client, owner, tm["membership"]["id"])
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        "/api/v1/positions", json={"department_id": dept.json()["id"], "title": "Engineer"}, headers=h
    )
    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": pos.json()["id"],
            "first_name": "Test",
            "last_name": "Teammate",
            "work_email": "react_tm6@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )

    resp = await client.post(f"{EMPLOYEES}/{emp.json()['id']}/grant-login", json={"role": "employee"}, headers=h)

    assert resp.status_code == 409
    assert resp.json()["code"] == "MEMBERSHIP_DEACTIVATED"
