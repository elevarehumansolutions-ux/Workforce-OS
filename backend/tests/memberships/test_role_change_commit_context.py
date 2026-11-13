"""Regression test: changing a teammate's role answers 200 even with production commits.

``PATCH /memberships/{id}`` saved the change, committed, and then re-read the membership
(``db.refresh``). With the tenant context gone after the commit (see
``tests.conftest.commit_like_production``) row-level security hid the row, the re-read failed
and the person saw a 500 even though the role HAD changed.
"""
from unittest.mock import MagicMock

import pytest

import app.modules.tenancy_identity.router as membership_router
from tests.conftest import commit_like_production, register_verified_and_login

AUTH = "/api/v1/auth"
MEMBERSHIPS = "/api/v1/memberships"


@pytest.mark.asyncio
async def test_role_change_answers_200_after_a_production_style_commit(client, db_session, monkeypatch):
    owner = await register_verified_and_login(client, email="role_ctx_owner@example.com")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(MEMBERSHIPS, json={"email": "role_ctx_mate@example.com", "role": "manager"}, headers=headers)
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    await client.post(
        f"{AUTH}/accept-invite",
        json={"token": raw_token, "full_name": "Role Mate", "password": "Password123#", "confirm_password": "Password123#"},
    )
    listing = await client.get(MEMBERSHIPS, headers=headers)
    mate = [m for m in listing.json()["data"] if m["user"]["email"] == "role_ctx_mate@example.com"][0]

    commit_like_production(db_session, monkeypatch)
    resp = await client.patch(f"{MEMBERSHIPS}/{mate['id']}", json={"role": "employee"}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "employee"
