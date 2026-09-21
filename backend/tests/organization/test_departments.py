"""HTTP-level tests for /departments CRUD and the delete-blocked-while-
referenced rule."""
import pytest

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
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
async def test_create_department_requires_hr_admin_role(client, monkeypatch):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dept_owner1@example.com")
    manager = await _invite_and_accept(client, monkeypatch, owner, "dept_mgr1@example.com", "manager")

    resp = await client.post(
        DEPARTMENTS, json={"name": "Ops"}, headers=_auth_header(manager["access_token"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_department_with_revenue_allocation(client):
    """Exercises the Decimal field end to end (also the jsonable_encoder
    fix on the audit-log side, indirectly)."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dept_owner2@example.com")
    h = _auth_header(owner["access_token"])

    resp = await client.post(
        DEPARTMENTS,
        json={"name": "Operations", "is_critical": True, "revenue_allocation_percentage": "45.50"},
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_critical"] is True
    assert body["revenue_allocation_percentage"] == "45.50"

    # Non-critical department created with no allocation stays genuinely
    # NULL, not a fake 0.00 (08_DECISIONS.md-adjacent design intent).
    resp2 = await client.post(DEPARTMENTS, json={"name": "Admin"}, headers=h)
    assert resp2.status_code == 200
    assert resp2.json()["is_critical"] is False
    assert resp2.json()["revenue_allocation_percentage"] is None


@pytest.mark.asyncio
async def test_update_and_get_department(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dept_owner3@example.com")
    h = _auth_header(owner["access_token"])

    create_resp = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    department_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"{DEPARTMENTS}/{department_id}", json={"is_critical": True}, headers=h
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_critical"] is True
    assert update_resp.json()["name"] == "Sales"

    get_resp = await client.get(f"{DEPARTMENTS}/{department_id}", headers=h)
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_department_blocked_while_position_active(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dept_owner4@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Engineering"}, headers=h)
    department_id = dept.json()["id"]
    await client.post(POSITIONS, json={"department_id": department_id, "title": "Engineer"}, headers=h)

    resp = await client.delete(f"{DEPARTMENTS}/{department_id}", headers=h)
    assert resp.status_code == 409
    assert "active position" in resp.json()["message"]


@pytest.mark.asyncio
async def test_delete_department_succeeds_once_positions_removed(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dept_owner5@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Marketing"}, headers=h)
    department_id = dept.json()["id"]
    pos = await client.post(POSITIONS, json={"department_id": department_id, "title": "Marketer"}, headers=h)

    await client.delete(f"{POSITIONS}/{pos.json()['id']}", headers=h)

    resp = await client.delete(f"{DEPARTMENTS}/{department_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is not None
