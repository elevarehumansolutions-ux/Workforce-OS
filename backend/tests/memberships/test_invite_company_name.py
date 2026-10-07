"""Regression test: the invite email carries the company name even with production commits.

``POST /memberships`` used to look the organization up after ``commit()``. With
the tenant context gone (see ``tests.conftest.commit_like_production``) row-level
security hid the row, the lookup returned ``None`` and the email silently lost
the company name.
"""
from unittest.mock import MagicMock

import pytest

import app.modules.tenancy_identity.router as membership_router
from tests.conftest import commit_like_production, register_verified_and_login

MEMBERSHIPS = "/api/v1/memberships"
BUSINESS_DNA = "/api/v1/business-dna"


@pytest.mark.asyncio
async def test_invite_email_includes_company_name_after_commit(client, db_session, monkeypatch):
    """The invite email task receives the organization's name, not None."""
    owner = await register_verified_and_login(client, email="invite_ctx_owner@example.com")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    named = await client.put(BUSINESS_DNA, json={"organization_name": "Acme Corp"}, headers=headers)
    assert named.status_code == 200

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    commit_like_production(db_session, monkeypatch)

    resp = await client.post(
        MEMBERSHIPS, json={"email": "invitee_ctx@example.com", "role": "employee"}, headers=headers
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "invited"
    assert mock_dispatch.delay.call_args.args[0] == "invitee_ctx@example.com"
    assert mock_dispatch.delay.call_args.args[2] == "Acme Corp"
