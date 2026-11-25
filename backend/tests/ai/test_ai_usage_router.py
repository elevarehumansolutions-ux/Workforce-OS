"""HTTP-level tests for GET /ai-usage."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import update

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.repository import AIUsageLogRepository
from app.modules.tenancy_identity.models import Membership

AI_USAGE = "/api/v1/ai-usage"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _invite_and_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    from unittest.mock import MagicMock
    import app.modules.tenancy_identity.router as membership_router_module

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        "/api/v1/memberships",
        json={"email": email, "role": role},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Test Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return accept_resp.json()


@pytest.mark.asyncio
async def test_ai_usage_requires_authentication(client):
    """GET /ai-usage rejects an unauthenticated request with 401."""
    resp = await client.get(AI_USAGE)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_customer_role_can_read_usage(client, monkeypatch):
    """A company's HR administrator and business executive are both refused: usage is Elevare's own."""
    owner = await register_verified_and_login(client, email="ai_usage_owner1@example.com")
    exec_user = await _invite_and_accept(
        client, monkeypatch, owner, "ai_usage_exec1@example.com", "business_executive"
    )
    for person in (owner, exec_user):
        resp = await client.get(AI_USAGE, headers=_auth_header(person["access_token"]))
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_platform_role_reads_the_organizations_usage_log(client, db_session):
    """Elevare's platform role can list the organization's usage log."""
    owner = await register_verified_and_login(client, email="ai_usage_owner2@example.com")
    org_id = uuid.UUID(owner["organization"]["id"])

    await set_org_context(db_session, org_id)
    # No request can give this role (customers are refused), so set it as Elevare would: in the database.
    await db_session.execute(
        update(Membership).where(Membership.organization_id == org_id).values(role="system_administrator")
    )
    repo = AIUsageLogRepository(db_session)
    await repo.create_usage_log(
        organization_id=org_id, purpose="ai_suggestion_generation", model="claude-sonnet-5",
        prompt_tokens=1000, completion_tokens=200, estimated_cost_usd=Decimal("0.0040"),
    )
    await repo.create_usage_log(
        organization_id=org_id, purpose="ai_suggestion_generation", model="claude-fable-5-1",
        prompt_tokens=500, completion_tokens=100, estimated_cost_usd=Decimal("0.0010"),
    )

    resp = await client.get(AI_USAGE, headers=_auth_header(owner["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 2
    assert {row["model"] for row in body["data"]} == {"claude-sonnet-5", "claude-fable-5-1"}
