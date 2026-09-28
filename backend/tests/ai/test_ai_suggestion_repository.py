"""Repository-level tests for AISuggestionRepository.create_pending_suggestion.

Exercises the pending-duplicate partial unique index directly, since this
is the one guarantee the whole idempotency design depends on (08_DECISIONS.md
2026-09-07, corrected 2026-09-23) — a repository-level test is more
direct here than going through the HTTP layer, since no router exists yet.
"""
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.models import AISuggestion
from app.modules.ai.repository import AISuggestionRepository

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_create_pending_suggestion_rejects_duplicate_target(client, db_session):
    """A second create_pending_suggestion call for the same target is absorbed, not duplicated."""
    owner = await register_verified_and_login(client, email="ai_repo_owner1@example.com")
    h = _auth_header(owner["access_token"])
    organization_id = owner["organization"]["id"]

    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS,
        json={"department_id": dept.json()["id"], "title": "General Manager"},
        headers=h,
    )
    position_id = pos.json()["id"]

    await set_org_context(db_session, organization_id)
    repo = AISuggestionRepository(db_session)

    suggestion = {
        "organization_id": organization_id,
        "suggestion_type": "critical_position",
        "position_id": position_id,
        "suggested_criticality_type": "revenue_generating",
        "suggested_risk_level": "high",
        "rationale": "Only GM role in a revenue-critical department.",
    }

    first = await repo.create_pending_suggestion(suggestion)
    assert first is not None
    assert first.id is not None

    second = await repo.create_pending_suggestion(suggestion)
    assert second is None

    count = await db_session.scalar(
        select(func.count())
        .select_from(AISuggestion)
        .where(
            AISuggestion.organization_id == organization_id,
            AISuggestion.position_id == position_id,
            AISuggestion.status == "pending",
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_create_pending_suggestion_rejects_duplicate_missing_department_target(
    client, db_session
):
    """Same guarantee for missing_department, where both position_id and department_id are null.

    This is the exact case the NULLS NOT DISTINCT fix (08_DECISIONS.md
    2026-09-23) exists for — without it, two nulls in those columns were
    never treated as a duplicate.
    """
    owner = await register_verified_and_login(client, email="ai_repo_owner2@example.com")
    organization_id = owner["organization"]["id"]

    await set_org_context(db_session, organization_id)
    repo = AISuggestionRepository(db_session)

    suggestion = {
        "organization_id": organization_id,
        "suggestion_type": "missing_department",
        "suggested_department_name": "Customer Success",
        "rationale": "No department currently owns post-sale retention.",
    }

    first = await repo.create_pending_suggestion(suggestion)
    assert first is not None

    second = await repo.create_pending_suggestion(suggestion)
    assert second is None

    count = await db_session.scalar(
        select(func.count())
        .select_from(AISuggestion)
        .where(
            AISuggestion.organization_id == organization_id,
            AISuggestion.suggested_department_name == "Customer Success",
            AISuggestion.status == "pending",
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_database_rejects_a_critical_position_without_type_and_risk(client, db_session):
    """The CHECK constraint is the backstop behind the schema's requirement."""
    owner = await register_verified_and_login(client, email="ai_repo_owner3@example.com")
    h = _auth_header(owner["access_token"])
    organization_id = owner["organization"]["id"]
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "GM"}, headers=h
    )
    await set_org_context(db_session, organization_id)

    with pytest.raises(IntegrityError):
        # A savepoint, so the failed insert doesn't poison the test's transaction.
        async with db_session.begin_nested():
            await AISuggestionRepository(db_session).create_pending_suggestion(
                {
                    "organization_id": organization_id,
                    "suggestion_type": "critical_position",
                    "position_id": pos.json()["id"],
                    "rationale": "no type, no risk",
                }
            )


@pytest.mark.asyncio
async def test_database_rejects_a_revenue_allocation_without_a_percentage(client, db_session):
    """The CHECK constraint is the backstop behind the schema's requirement."""
    owner = await register_verified_and_login(client, email="ai_repo_owner4@example.com")
    h = _auth_header(owner["access_token"])
    organization_id = owner["organization"]["id"]
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    await set_org_context(db_session, organization_id)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await AISuggestionRepository(db_session).create_pending_suggestion(
                {
                    "organization_id": organization_id,
                    "suggestion_type": "revenue_allocation",
                    "department_id": dept.json()["id"],
                    "rationale": "no percentage",
                }
            )
