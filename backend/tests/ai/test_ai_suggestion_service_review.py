"""Service-level tests for rejecting a suggestion.

Covers the success path (including the audit entry) and the two error
paths the service has to tell apart: not found (404) versus already
reviewed (409). The "already reviewed" case is also what a reviewer who
loses a race with another reviewer experiences.
"""
import uuid

import pytest
from sqlalchemy import select

from tests.conftest import register_verified_and_login, set_org_context
from app.core.exceptions import (
    SuggestionAlreadyReviewedException,
    SuggestionNotFoundException,
)
from app.modules.ai.repository import AISuggestionRepository
from app.modules.ai.service import AISuggestionService
from app.modules.audit_and_notification.models import AuditLog


async def _org_with_pending_suggestion(client, db_session, email):
    """Register an org, create one pending suggestion in it, return what a test needs."""
    owner = await register_verified_and_login(client, email=email)
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    await set_org_context(db_session, org_id)
    suggestion = await AISuggestionRepository(db_session).create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "Customer Success",
            "rationale": "test",
        }
    )
    return AISuggestionService(db_session), org_id, user_id, suggestion.id


async def _audit_rows(db_session, suggestion_id):
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "ai_suggestion", AuditLog.entity_id == suggestion_id
        )
    )
    return result.scalars().all()


@pytest.mark.asyncio
async def test_reject_returns_the_rejected_suggestion_and_audits_it(client, db_session):
    """A successful reject returns the updated suggestion and writes exactly one audit entry."""
    service, org_id, user_id, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_svc_rej1@example.com"
    )

    result = await service.reject_suggestion(suggestion_id, user_id)

    assert result.status == "rejected"
    assert result.reviewed_by_user_id == user_id
    assert result.reviewed_at is not None

    (entry,) = await _audit_rows(db_session, suggestion_id)
    assert entry.organization_id == org_id
    assert entry.actor_user_id == user_id
    assert entry.action == "reject"
    assert entry.changes == {"old": {"status": "pending"}, "new": {"status": "rejected"}}


@pytest.mark.asyncio
async def test_reject_unknown_suggestion_is_not_found(client, db_session):
    """An id that doesn't exist raises the 404 exception, and audits nothing."""
    service, _, user_id, _ = await _org_with_pending_suggestion(
        client, db_session, "ai_svc_rej2@example.com"
    )
    unknown = uuid.uuid4()

    with pytest.raises(SuggestionNotFoundException):
        await service.reject_suggestion(unknown, user_id)

    assert await _audit_rows(db_session, unknown) == []


@pytest.mark.asyncio
async def test_reject_already_reviewed_suggestion_is_a_conflict(client, db_session):
    """Rejecting twice raises the 409 exception — and the loser of a race lands here too."""
    service, _, user_id, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_svc_rej3@example.com"
    )
    await service.reject_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.reject_suggestion(suggestion_id, user_id)

    # Only the first decision was audited.
    assert len(await _audit_rows(db_session, suggestion_id)) == 1


@pytest.mark.asyncio
async def test_reject_another_orgs_suggestion_is_not_found(client, db_session):
    """RLS hides a foreign org's suggestion, so it's a 404 — not a 409 that would confirm it exists."""
    service, org_a, _, suggestion_id = await _org_with_pending_suggestion(
        client, db_session, "ai_svc_rej4a@example.com"
    )
    other = await register_verified_and_login(client, email="ai_svc_rej4b@example.com")

    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))
    with pytest.raises(SuggestionNotFoundException):
        await service.reject_suggestion(suggestion_id, uuid.UUID(other["user"]["id"]))

    await set_org_context(db_session, org_a)
    assert await _audit_rows(db_session, suggestion_id) == []
