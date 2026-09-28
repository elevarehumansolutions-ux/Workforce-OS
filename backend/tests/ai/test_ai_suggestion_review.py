"""Repository-level tests for AISuggestionRepository.reject_pending_suggestion.

The property that matters: the pending check lives inside the UPDATE, so
only a still-pending suggestion can be rejected, exactly once, and only by
a caller in the owning organization (RLS).
"""
import uuid

import pytest
from sqlalchemy import select, update

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.models import AISuggestion
from app.modules.ai.repository import AISuggestionRepository


async def _org_with_pending_suggestion(client, db_session, email):
    """Register an org and create one pending missing_department suggestion in it."""
    owner = await register_verified_and_login(client, email=email)
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    await set_org_context(db_session, org_id)
    repo = AISuggestionRepository(db_session)
    suggestion = await repo.create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "Customer Success",
            "rationale": "test",
        }
    )
    return repo, org_id, user_id, suggestion.id


async def _row_state(db_session, suggestion_id):
    row = (
        await db_session.execute(
            select(
                AISuggestion.status,
                AISuggestion.reviewed_at,
                AISuggestion.reviewed_by_user_id,
            ).where(AISuggestion.id == suggestion_id)
        )
    ).one()
    return row.status, row.reviewed_at, row.reviewed_by_user_id


@pytest.mark.asyncio
async def test_rejecting_a_pending_suggestion_records_who_and_when(client, db_session):
    """A pending suggestion becomes rejected, with reviewed_at/reviewed_by set (suppression needs both)."""
    repo, _, user_id, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_review1@example.com"
    )

    rejected = await repo.reject_pending_suggestion(suggestion_id, user_id)

    assert rejected is not None
    assert rejected.status == "rejected"
    assert rejected.reviewed_by_user_id == user_id
    assert rejected.reviewed_at is not None


@pytest.mark.asyncio
async def test_rejecting_twice_is_a_noop_the_second_time(client, db_session):
    """The second reject returns None and leaves the first decision untouched."""
    repo, _, user_id, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_review2@example.com"
    )

    await repo.reject_pending_suggestion(suggestion_id, user_id)
    _, first_reviewed_at, _ = await _row_state(db_session, suggestion_id)

    second = await repo.reject_pending_suggestion(suggestion_id, user_id)

    assert second is None
    status, reviewed_at, _ = await _row_state(db_session, suggestion_id)
    assert status == "rejected"
    assert reviewed_at == first_reviewed_at


@pytest.mark.asyncio
async def test_an_already_approved_suggestion_cannot_be_rejected(client, db_session):
    """Only pending suggestions transition — an approved one is left exactly as it was."""
    repo, _, user_id, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_review3@example.com"
    )
    await db_session.execute(
        update(AISuggestion).where(AISuggestion.id == suggestion_id).values(status="approved")
    )

    result = await repo.reject_pending_suggestion(suggestion_id, user_id)

    assert result is None
    status, _, _ = await _row_state(db_session, suggestion_id)
    assert status == "approved"


@pytest.mark.asyncio
async def test_unknown_suggestion_id_returns_none(client, db_session):
    """No such suggestion: nothing changes and the caller gets None."""
    repo, _, user_id, _ = await _org_with_pending_suggestion(
        client, db_session, "ai_review4@example.com"
    )

    assert await repo.reject_pending_suggestion(uuid.uuid4(), user_id) is None


@pytest.mark.asyncio
async def test_another_orgs_suggestion_cannot_be_rejected(client, db_session):
    """RLS makes a foreign org's suggestion invisible to the UPDATE — it matches nothing."""
    repo, org_a, user_a, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_review5a@example.com"
    )
    other = await register_verified_and_login(client, email="ai_review5b@example.com")
    org_b = uuid.UUID(other["organization"]["id"])

    await set_org_context(db_session, org_b)
    assert await repo.reject_pending_suggestion(suggestion_id, uuid.UUID(other["user"]["id"])) is None

    await set_org_context(db_session, org_a)
    status, reviewed_at, _ = await _row_state(db_session, suggestion_id)
    assert status == "pending"
    assert reviewed_at is None


@pytest.mark.asyncio
async def test_get_suggestion_by_id_returns_the_suggestion(client, db_session):
    """A suggestion is found by its id, whatever its status."""
    repo, _, user_id, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_review6@example.com"
    )

    found = await repo.get_suggestion_by_id(suggestion_id)
    assert found is not None
    assert found.status == "pending"

    await repo.reject_pending_suggestion(suggestion_id, user_id)
    assert (await repo.get_suggestion_by_id(suggestion_id)).status == "rejected"


@pytest.mark.asyncio
async def test_get_suggestion_by_id_unknown_or_foreign_returns_none(client, db_session):
    """Unknown ids, and another org's suggestion (RLS), both come back as None — indistinguishable."""
    repo, org_a, _, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_review7a@example.com"
    )
    other = await register_verified_and_login(client, email="ai_review7b@example.com")

    assert await repo.get_suggestion_by_id(uuid.uuid4()) is None

    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))
    assert await repo.get_suggestion_by_id(suggestion_id) is None

    await set_org_context(db_session, org_a)
    assert await repo.get_suggestion_by_id(suggestion_id) is not None
