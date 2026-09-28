"""Repository-level tests for has_recent_rejection and department-name normalization.

Uses fixed dates (not now()) for the quarter boundary so the
"this quarter" vs "previous quarter" cases are deterministic.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.models import AISuggestion
from app.modules.ai.repository import AISuggestionRepository

QUARTER_START = datetime(2026, 7, 1, tzinfo=UTC)


async def _seed_rejected_missing_department(db_session, organization_id, name, reviewed_at):
    """Create a pending missing_department suggestion, then mark it rejected at reviewed_at."""
    repo = AISuggestionRepository(db_session)
    created = await repo.create_pending_suggestion(
        {
            "organization_id": organization_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": name,
            "rationale": "test",
        }
    )
    await db_session.execute(
        update(AISuggestion)
        .where(AISuggestion.id == created.id)
        .values(status="rejected", reviewed_at=reviewed_at)
    )
    return repo


async def _lookup(repo, organization_id, name):
    return await repo.has_recent_rejection(
        organization_id, "missing_department", None, None, name, QUARTER_START
    )


@pytest.mark.asyncio
async def test_rejection_inside_current_quarter_blocks(client, db_session):
    """A rejection at/after the quarter start counts."""
    owner = await register_verified_and_login(client, email="ai_lookup1@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    repo = await _seed_rejected_missing_department(
        db_session, org_id, "Customer Success", datetime(2026, 8, 1, tzinfo=UTC)
    )
    assert await _lookup(repo, org_id, "Customer Success") is True


@pytest.mark.asyncio
async def test_rejection_before_current_quarter_does_not_block(client, db_session):
    """A rejection from a previous quarter no longer suppresses regeneration."""
    owner = await register_verified_and_login(client, email="ai_lookup2@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    repo = await _seed_rejected_missing_department(
        db_session, org_id, "Customer Success", datetime(2026, 6, 15, tzinfo=UTC)
    )
    assert await _lookup(repo, org_id, "Customer Success") is False


@pytest.mark.asyncio
async def test_rejection_of_a_different_target_does_not_block(client, db_session):
    """Only the exact same target is suppressed, not the whole suggestion type."""
    owner = await register_verified_and_login(client, email="ai_lookup3@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    repo = await _seed_rejected_missing_department(
        db_session, org_id, "Customer Success", datetime(2026, 8, 1, tzinfo=UTC)
    )
    assert await _lookup(repo, org_id, "Legal") is False


@pytest.mark.asyncio
async def test_rejection_lookup_ignores_case_and_whitespace(client, db_session):
    """A rejected name also suppresses case/spacing/Unicode variants of itself."""
    owner = await register_verified_and_login(client, email="ai_lookup4@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    repo = await _seed_rejected_missing_department(
        db_session, org_id, "Customer Success", datetime(2026, 8, 1, tzinfo=UTC)
    )
    assert await _lookup(repo, org_id, "  customer   SUCCESS ") is True
    assert await _lookup(repo, org_id, "Customer Success") is True
    # A genuinely different wording is a different target — normalization
    # handles formatting noise, not synonyms.
    assert await _lookup(repo, org_id, "Customer Success Team") is False


@pytest.mark.asyncio
async def test_pending_duplicate_ignores_case_and_whitespace(client, db_session):
    """The pending-duplicate index treats formatting variants of a name as one target."""
    owner = await register_verified_and_login(client, email="ai_lookup5@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    repo = AISuggestionRepository(db_session)

    base = {
        "organization_id": org_id,
        "suggestion_type": "missing_department",
        "rationale": "test",
    }
    first = await repo.create_pending_suggestion(
        {**base, "suggested_department_name": "Customer Success"}
    )
    assert first is not None
    assert first.suggested_department_name_normalized == "customer success"

    variant = await repo.create_pending_suggestion(
        {**base, "suggested_department_name": "  customer   SUCCESS "}
    )
    assert variant is None
