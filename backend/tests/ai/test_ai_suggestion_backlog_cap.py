"""Backlog cap on missing_department suggestions (08_DECISIONS.md 2026-09-25).

Scenario: Kelechi's queue already holds as many unreviewed "missing
department" ideas as the cap allows. The next run must add nothing more —
until he reviews some — while other suggestion types are unaffected.
"""
import uuid

import pytest
from sqlalchemy import select

from tests.conftest import register_verified_and_login, set_org_context
from app.core.config import settings
from app.modules.ai.repository import AISuggestionRepository
from app.modules.ai.schemas import AISuggestionCreateRequest
from app.modules.ai.service import AISuggestionService
from app.modules.tenancy_identity.models import Membership


async def _org_service(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    return org_id, h, AISuggestionService(db_session)


def _missing_department(name):
    return AISuggestionCreateRequest(
        suggestion_type="missing_department",
        suggested_department_name=name,
        rationale="Nobody owns this yet.",
    )


@pytest.mark.asyncio
async def test_no_more_missing_departments_once_the_backlog_is_full(client, db_session, monkeypatch):
    """At the cap, a new idea is a quiet no-op; reviewing one frees a slot."""
    monkeypatch.setattr(settings, "ai_max_pending_missing_departments", 2)
    org_id, _, service = await _org_service(client, db_session, "ai_cap1@example.com")

    first = await service.create_suggestion_if_eligible(org_id, _missing_department("Legal"))
    second = await service.create_suggestion_if_eligible(org_id, _missing_department("Support"))
    third = await service.create_suggestion_if_eligible(org_id, _missing_department("Innovation Lab"))

    assert first is not None and second is not None
    assert third is None

    # Rejecting one frees a slot (the rejected name itself stays suppressed this quarter).
    reviewer_id = await db_session.scalar(
        select(Membership.user_id).where(Membership.organization_id == org_id)
    )
    await AISuggestionRepository(db_session).reject_pending_suggestion(first.id, reviewer_id)

    assert await service.create_suggestion_if_eligible(org_id, _missing_department("Innovation Lab")) is not None


@pytest.mark.asyncio
async def test_the_cap_does_not_touch_other_suggestion_types(client, db_session, monkeypatch):
    """A full missing_department backlog doesn't block a critical_position suggestion."""
    monkeypatch.setattr(settings, "ai_max_pending_missing_departments", 1)
    org_id, h, service = await _org_service(client, db_session, "ai_cap2@example.com")
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        "/api/v1/positions", json={"department_id": dept.json()["id"], "title": "GM"}, headers=h
    )

    await service.create_suggestion_if_eligible(org_id, _missing_department("Legal"))
    critical = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=uuid.UUID(pos.json()["id"]),
            suggested_criticality_type="revenue_generating",
            suggested_risk_level="high",
            rationale="Owns delivery.",
        ),
    )

    assert critical is not None
