"""HTTP-level tests for GET /audit-log."""
from datetime import datetime, timedelta, UTC
from uuid import uuid4

import pytest

from app.modules.audit_and_notification.models import AuditLog
from app.modules.audit_and_notification.service import AuditService

AUDIT_LOG = "/api/v1/audit-log"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _invite_and_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    """Add a teammate with a given role and log them in.

    For testing role gates other than the founder's own hr_administrator.
    """
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
async def test_list_audit_log_requires_authentication(client):
    """An unauthenticated request to the audit log endpoint returns 401."""
    resp = await client.get(AUDIT_LOG)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_audit_log_rejects_employee_role(client, monkeypatch):
    """A member with the employee role gets 403 when listing the audit log."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="audit_owner1@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "audit_emp1@example.com", "employee")

    resp = await client.get(AUDIT_LOG, headers=_auth_header(employee["access_token"]))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_audit_log_allows_business_executive_role(client, monkeypatch):
    """A member with the business_executive role can list the audit log."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="audit_owner2@example.com")
    exec_ = await _invite_and_accept(
        client, monkeypatch, owner, "audit_exec2@example.com", "business_executive"
    )

    resp = await client.get(AUDIT_LOG, headers=_auth_header(exec_["access_token"]))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_audit_log_returns_org_scoped_entries(client, db_session):
    """RLS proof: an admin only ever sees their own org's audit trail.

    Even though both orgs' rows sit in the same table.
    """
    from tests.conftest import register_verified_and_login, set_org_context

    owner_a = await register_verified_and_login(client, email="audit_owner_a@example.com")
    owner_b = await register_verified_and_login(client, email="audit_owner_b@example.com")

    await set_org_context(db_session, owner_a["organization"]["id"])
    await AuditService(db_session).log_action(
        organization_id=owner_a["organization"]["id"],
        actor_user_id=owner_a["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=uuid4(),
    )

    await set_org_context(db_session, owner_b["organization"]["id"])
    await AuditService(db_session).log_action(
        organization_id=owner_b["organization"]["id"],
        actor_user_id=owner_b["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=uuid4(),
    )

    resp = await client.get(AUDIT_LOG, headers=_auth_header(owner_a["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["organization_id"] == owner_a["organization"]["id"]


@pytest.mark.asyncio
async def test_list_audit_log_filters_by_entity_type_and_entity_id(client, db_session):
    """The entity_type and entity_id query params each narrow results to matching rows only."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="audit_owner3@example.com")
    await set_org_context(db_session, owner["organization"]["id"])
    service = AuditService(db_session)

    dept_id = uuid4()
    await service.log_action(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=dept_id,
    )
    await service.log_action(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="create",
        entity_type="position",
        entity_id=uuid4(),
    )

    resp = await client.get(
        AUDIT_LOG,
        params={"entity_type": "department"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["entity_type"] == "department"

    resp2 = await client.get(
        AUDIT_LOG,
        params={"entity_id": str(dept_id)},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp2.json()["pagination"]["total"] == 1
    assert resp2.json()["data"][0]["entity_id"] == str(dept_id)


@pytest.mark.asyncio
async def test_list_audit_log_filters_by_actor_user_id(client, db_session, monkeypatch):
    """The actor_user_id query param returns only entries logged by that actor."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="audit_owner4@example.com")
    other = await _invite_and_accept(client, monkeypatch, owner, "audit_other4@example.com", "manager")

    await set_org_context(db_session, owner["organization"]["id"])
    service = AuditService(db_session)
    await service.log_action(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=uuid4(),
    )
    await service.log_action(
        organization_id=owner["organization"]["id"],
        actor_user_id=other["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=uuid4(),
    )

    resp = await client.get(
        AUDIT_LOG,
        params={"actor_user_id": other["user"]["id"]},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["actor_user_id"] == other["user"]["id"]


@pytest.mark.asyncio
async def test_list_audit_log_date_range_filter(client, db_session):
    """Seeds rows with explicit created_at values to prove date_from narrows results.

    Bypasses log_action, which deliberately never accepts a caller-supplied
    timestamp.
    """
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="audit_owner5@example.com")
    await set_org_context(db_session, owner["organization"]["id"])

    old_entry = AuditLog(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=uuid4(),
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    recent_entry = AuditLog(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="create",
        entity_type="department",
        entity_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    db_session.add_all([old_entry, recent_entry])
    await db_session.flush()

    resp = await client.get(
        AUDIT_LOG,
        params={"date_from": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == str(recent_entry.id)


@pytest.mark.asyncio
async def test_list_audit_log_cursor_pagination(client, db_session):
    """Cursor pagination returns all rows exactly once across pages, with no next_cursor on the last page."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="audit_owner6@example.com")
    await set_org_context(db_session, owner["organization"]["id"])
    service = AuditService(db_session)

    for _ in range(3):
        await service.log_action(
            organization_id=owner["organization"]["id"],
            actor_user_id=owner["user"]["id"],
            action="create",
            entity_type="department",
            entity_id=uuid4(),
        )

    page1 = await client.get(
        AUDIT_LOG,
        params={"limit": 2},
        headers=_auth_header(owner["access_token"]),
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["pagination"]["total"] == 3
    assert body1["pagination"]["count"] == 2
    assert body1["pagination"]["next_cursor"] is not None

    page2 = await client.get(
        AUDIT_LOG,
        params={"limit": 2, "cursor": body1["pagination"]["next_cursor"]},
        headers=_auth_header(owner["access_token"]),
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert body2["pagination"]["count"] == 1
    assert body2["pagination"]["next_cursor"] is None

    seen_ids = {row["id"] for row in body1["data"]} | {row["id"] for row in body2["data"]}
    assert len(seen_ids) == 3
