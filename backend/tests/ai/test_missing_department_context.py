"""Gathering everything one missing-department run needs.

Scenario: Kelechi's company has Operations, one objective, and rejected
"Customer Support" last month (still within this fiscal quarter). The
gatherer hands back all three — and, for a brand-new org with none of it,
still a real context, never None: this type has no "nothing to ask about".
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.generation import gather_missing_department_context
from app.modules.ai.models import AISuggestion
from app.modules.ai.repository import AISuggestionRepository
from app.modules.tenancy_identity.models import Membership

DEPARTMENTS = "/api/v1/departments"
OKRS = "/api/v1/okrs"


async def _org(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    return org_id, h


@pytest.mark.asyncio
async def test_existing_departments_and_objectives_are_carried_into_the_context(client, db_session):
    """A real department and objective both reach the gathered context."""
    org_id, h = await _org(client, db_session, "miss_ctx1@example.com")
    await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)
    await client.post(OKRS, json={"title": "Cut late deliveries by 20%"}, headers=h)

    context = await gather_missing_department_context(db_session, org_id)

    assert context.existing_department_names == ["Operations"]
    assert context.objective_titles == ["Cut late deliveries by 20%"]
    assert context.already_rejected_department_names == []


@pytest.mark.asyncio
async def test_a_recently_rejected_name_is_carried_into_the_context(client, db_session):
    """A name rejected this quarter shows up so Claude knows not to repeat it."""
    org_id, h = await _org(client, db_session, "miss_ctx2@example.com")
    reviewer_id = await db_session.scalar(
        select(Membership.user_id).where(Membership.organization_id == org_id)
    )
    suggestion = await AISuggestionRepository(db_session).create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "Customer Support",
            "rationale": "No one owns retention.",
        }
    )
    await AISuggestionRepository(db_session).reject_pending_suggestion(suggestion.id, reviewer_id)

    context = await gather_missing_department_context(db_session, org_id)

    assert context.already_rejected_department_names == ["Customer Support"]


@pytest.mark.asyncio
async def test_a_rejection_from_last_quarter_is_not_carried_in(client, db_session):
    """Only this fiscal quarter's rejections count — an old one no longer suppresses."""
    org_id, h = await _org(client, db_session, "miss_ctx3@example.com")
    reviewer_id = await db_session.scalar(
        select(Membership.user_id).where(Membership.organization_id == org_id)
    )
    suggestion = await AISuggestionRepository(db_session).create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "Customer Support",
            "rationale": "No one owns retention.",
        }
    )
    await AISuggestionRepository(db_session).reject_pending_suggestion(suggestion.id, reviewer_id)
    await db_session.execute(
        AISuggestion.__table__.update()
        .where(AISuggestion.id == suggestion.id)
        .values(reviewed_at=datetime.now(UTC) - timedelta(days=400))
    )

    context = await gather_missing_department_context(db_session, org_id)

    assert context.already_rejected_department_names == []


@pytest.mark.asyncio
async def test_a_brand_new_org_still_gets_a_real_context(client, db_session):
    """No departments, no OKRs, no rejections — still a context, not None."""
    org_id, _ = await _org(client, db_session, "miss_ctx4@example.com")

    context = await gather_missing_department_context(db_session, org_id)

    assert (
        context.existing_department_names,
        context.already_rejected_department_names,
        context.objective_titles,
    ) == ([], [], [])
