"""HTTP-level tests: a pending AI suggestion blocks deleting its target.

Scenario: Adaeze tries to delete the "Operations" department (or the General
Manager position) while the AI has a pending suggestion about it. She is told
to review the suggestion first; once it's decided, deletion works again.
"""
import uuid
from decimal import Decimal

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.schemas import AISuggestionCreateRequest
from app.modules.ai.service import AISuggestionService

SUGGESTIONS = "/api/v1/ai-suggestions"
DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org(client, db_session, email):
    """An org with departments Ops/Finance, one position under Ops, and pending suggestions for Ops and the position."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    org_id = uuid.UUID(owner["organization"]["id"])
    ops = (await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)).json()
    finance = (await client.post(DEPARTMENTS, json={"name": "Finance"}, headers=h)).json()
    gm = (await client.post(POSITIONS, json={"department_id": finance["id"], "title": "GM"}, headers=h)).json()
    await set_org_context(db_session, org_id)
    service = AISuggestionService(db_session)
    allocation = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="revenue_allocation",
            department_id=uuid.UUID(ops["id"]),
            suggested_revenue_allocation_percentage=Decimal("40"),
            rationale="x",
        ),
    )
    critical = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=uuid.UUID(gm["id"]),
            suggested_criticality_type="revenue_generating",
            suggested_risk_level="high",
            rationale="x",
        ),
    )
    return h, ops["id"], finance["id"], gm["id"], allocation.id, critical.id


@pytest.mark.asyncio
async def test_a_department_with_a_pending_suggestion_cannot_be_deleted(client, db_session):
    """409 naming the reason — and once the suggestion is reviewed, the delete goes through."""
    h, ops_id, _, _, allocation_id, _ = await _org(client, db_session, "ai_guard1@example.com")

    blocked = await client.delete(f"{DEPARTMENTS}/{ops_id}", headers=h)
    assert blocked.status_code == 409
    assert "pending AI suggestion" in blocked.json()["message"]

    await client.post(f"{SUGGESTIONS}/{allocation_id}/reject", headers=h)

    assert (await client.delete(f"{DEPARTMENTS}/{ops_id}", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_a_position_with_a_pending_suggestion_cannot_be_deleted(client, db_session):
    """Same rule for positions; approving the suggestion also clears the block."""
    h, _, _, gm_id, _, critical_id = await _org(client, db_session, "ai_guard2@example.com")

    blocked = await client.delete(f"{POSITIONS}/{gm_id}", headers=h)
    assert blocked.status_code == 409
    assert "pending AI suggestion" in blocked.json()["message"]

    await client.post(f"{SUGGESTIONS}/{critical_id}/approve", headers=h)

    assert (await client.delete(f"{POSITIONS}/{gm_id}", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_reasons_are_reported_together(client, db_session):
    """A department blocked by an active position *and* a pending suggestion says both."""
    h, ops_id, _, _, _, _ = await _org(client, db_session, "ai_guard3@example.com")
    await client.post(POSITIONS, json={"department_id": ops_id, "title": "Clerk"}, headers=h)

    resp = await client.delete(f"{DEPARTMENTS}/{ops_id}", headers=h)

    assert resp.status_code == 409
    message = resp.json()["message"]
    assert "active position" in message and "pending AI suggestion" in message


@pytest.mark.asyncio
async def test_a_suggestion_about_one_department_does_not_block_another(client, db_session):
    """Only the suggestion's own target is blocked: Finance has none, so it can be deleted."""
    h, _, finance_id, gm_id, _, critical_id = await _org(client, db_session, "ai_guard4@example.com")
    await client.post(f"{SUGGESTIONS}/{critical_id}/reject", headers=h)
    await client.delete(f"{POSITIONS}/{gm_id}", headers=h)

    assert (await client.delete(f"{DEPARTMENTS}/{finance_id}", headers=h)).status_code == 200
