"""HTTP-level tests that Team Management mutations are audit-logged.

Invites, direct adds, role changes, deactivation and reactivation all leave
an ``audit_log`` entry with who did it and the old/new state
(08_DECISIONS.md 2026-10-02). Reactivation via ``/reactivate`` is covered in
test_membership_reactivation.py.
"""
import json
from unittest.mock import MagicMock

import pytest

from tests.conftest import register_verified_and_login

AUTH = "/api/v1/auth"
MEMBERSHIPS = "/api/v1/memberships"
AUDIT = "/api/v1/audit-log"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _entries(client, h, entity_type: str, action: str) -> list[dict]:
    resp = await client.get(AUDIT, params={"entity_type": entity_type}, headers=h)
    assert resp.status_code == 200
    return [e for e in resp.json()["data"] if e["action"] == action]


@pytest.mark.asyncio
async def test_inviting_a_new_email_is_logged_without_the_token(client, monkeypatch):
    """The invite entry records who was invited as what, and never the secret link token."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    owner = await register_verified_and_login(client, email="aud_owner1@example.com")
    h = _auth_header(owner["access_token"])

    await client.post(MEMBERSHIPS, json={"email": "aud_new1@example.com", "role": "manager"}, headers=h)

    entries = await _entries(client, h, "invite", "invite")
    assert len(entries) == 1
    assert entries[0]["actor_user_id"] == owner["user"]["id"]
    assert entries[0]["changes"]["new"]["email"] == "aud_new1@example.com"
    assert entries[0]["changes"]["new"]["role"] == "manager"
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    assert raw_token not in json.dumps(entries[0])


@pytest.mark.asyncio
async def test_an_existing_account_joining_is_logged_as_the_invite_and_then_their_own_acceptance(client, monkeypatch):
    """The invite is logged (has_account true); when they accept, an 'add' is logged with them as the actor."""
    from tests.memberships.join_helper import join_existing

    owner = await register_verified_and_login(client, email="aud_owner2@example.com")
    existing = await register_verified_and_login(client, email="aud_existing2@example.com")
    h = _auth_header(owner["access_token"])

    joined = await join_existing(client, monkeypatch, owner, "aud_existing2@example.com", "employee")

    invites = await _entries(client, h, "invite", "invite")
    assert len(invites) == 1 and invites[0]["changes"]["new"]["has_account"] is True
    entries = await _entries(client, h, "membership", "add")
    assert len(entries) == 1
    assert entries[0]["entity_id"] == joined["membership"]["id"]
    assert entries[0]["changes"]["new"]["role"] == "employee"
    assert entries[0]["actor_user_id"] == existing["user"]["id"]


@pytest.mark.asyncio
async def test_role_change_deactivation_and_reactivation_are_logged(client, monkeypatch):
    """PATCH logs 'update' and 'deactivate'; /reactivate logs 'reactivate'; each with old and new state."""
    from tests.memberships.join_helper import join_existing

    owner = await register_verified_and_login(client, email="aud_owner3@example.com")
    await register_verified_and_login(client, email="aud_member3@example.com")
    h = _auth_header(owner["access_token"])
    added = await join_existing(client, monkeypatch, owner, "aud_member3@example.com", "employee")
    membership_id = added["membership"]["id"]

    await client.patch(f"{MEMBERSHIPS}/{membership_id}", json={"role": "manager"}, headers=h)
    await client.patch(f"{MEMBERSHIPS}/{membership_id}", json={"is_deactivated": True}, headers=h)
    await client.post(f"{MEMBERSHIPS}/{membership_id}/reactivate", headers=h)

    update = (await _entries(client, h, "membership", "update"))[0]
    assert update["changes"]["old"]["role"] == "employee"
    assert update["changes"]["new"]["role"] == "manager"
    deactivate = (await _entries(client, h, "membership", "deactivate"))[0]
    assert deactivate["changes"]["old"]["deactivated_at"] is None
    assert deactivate["changes"]["new"]["deactivated_at"] is not None
    reactivate = (await _entries(client, h, "membership", "reactivate"))[0]
    assert reactivate["changes"]["old"]["deactivated_at"] is not None
    assert reactivate["changes"]["new"]["deactivated_at"] is None
    assert reactivate["actor_user_id"] == owner["user"]["id"]
