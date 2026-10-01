"""Persistence of one LLM call's usage row.

Scenario: Adaeze's suggestion run finishes on the strong model (1,200 tokens
in, 300 out, $0.0054). One row must land in ai_usage_log — visible to her
organization, invisible to every other one.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.models import AIUsageLog
from app.modules.ai.repository import AIUsageLogRepository


async def _org(client, email):
    owner = await register_verified_and_login(client, email=email)
    return uuid.UUID(owner["organization"]["id"])


def _call(org_id, **overrides):
    values = dict(
        organization_id=org_id,
        purpose="ai_suggestion_generation",
        model="claude-sonnet-5",
        prompt_tokens=1_200,
        completion_tokens=300,
        estimated_cost_usd=Decimal("0.0054"),
    )
    return {**values, **overrides}


@pytest.mark.asyncio
async def test_a_call_is_recorded_with_its_model_tokens_and_cost(client, db_session):
    """The row carries exactly what was passed in; cache columns default to zero."""
    org_id = await _org(client, "ai_usage1@example.com")
    await set_org_context(db_session, org_id)

    row = await AIUsageLogRepository(db_session).create_usage_log(**_call(org_id))

    saved = await db_session.get(AIUsageLog, row.id)
    assert (saved.organization_id, saved.purpose, saved.model) == (
        org_id,
        "ai_suggestion_generation",
        "claude-sonnet-5",
    )
    assert (saved.prompt_tokens, saved.completion_tokens) == (1_200, 300)
    assert (saved.cache_write_tokens, saved.cache_read_tokens) == (0, 0)
    assert saved.estimated_cost_usd == Decimal("0.0054")
    assert saved.created_at is not None


@pytest.mark.asyncio
async def test_cache_tokens_and_an_unpriced_model_are_stored_too(client, db_session):
    """Cache buckets are kept in their own columns; an unknown price is stored as NULL."""
    org_id = await _org(client, "ai_usage2@example.com")
    await set_org_context(db_session, org_id)

    row = await AIUsageLogRepository(db_session).create_usage_log(
        **_call(org_id, cache_write_tokens=500, cache_read_tokens=4_000, estimated_cost_usd=None)
    )

    saved = await db_session.get(AIUsageLog, row.id)
    assert (saved.cache_write_tokens, saved.cache_read_tokens) == (500, 4_000)
    assert saved.estimated_cost_usd is None


@pytest.mark.asyncio
async def test_two_identical_calls_are_two_rows(client, db_session):
    """Every real API call costs money, so a repeat is never de-duplicated."""
    org_id = await _org(client, "ai_usage3@example.com")
    await set_org_context(db_session, org_id)
    repo = AIUsageLogRepository(db_session)

    await repo.create_usage_log(**_call(org_id))
    await repo.create_usage_log(**_call(org_id))

    count = await db_session.scalar(select(func.count()).select_from(AIUsageLog))
    assert count == 2


@pytest.mark.asyncio
async def test_another_organization_cannot_see_the_row(client, db_session):
    """Tenant isolation: under org B's context, org A's usage row is invisible."""
    org_a = await _org(client, "ai_usage4a@example.com")
    org_b = await _org(client, "ai_usage4b@example.com")
    await set_org_context(db_session, org_a)
    await AIUsageLogRepository(db_session).create_usage_log(**_call(org_a))

    await set_org_context(db_session, org_b)

    count = await db_session.scalar(select(func.count()).select_from(AIUsageLog))
    assert count == 0


@pytest.mark.asyncio
async def test_list_usage_logs_is_paginated_and_org_scoped(client, db_session):
    """list_usage_logs paginates and stays within one org.

    Doesn't assert exact ordering between these particular rows: they're
    all inserted in the same uncommitted transaction, and Postgres's
    ``now()`` is transaction-scoped, not per-statement — same reasoning
    already documented elsewhere in this codebase for same-``created_at``
    ties (see the department-candidate-query test note, 08_DECISIONS.md).
    The ``created_at.desc()`` ordering itself matches every other
    ``list_*`` method in this codebase and isn't re-verified here.
    """
    org_a = await _org(client, "ai_usage5a@example.com")
    org_b = await _org(client, "ai_usage5b@example.com")
    await set_org_context(db_session, org_a)
    repo = AIUsageLogRepository(db_session)

    await repo.create_usage_log(**_call(org_a, model="claude-sonnet-5"))
    await repo.create_usage_log(**_call(org_a, model="claude-fable-5-1"))
    await repo.create_usage_log(**_call(org_a, model="claude-opus-5-5"))
    await set_org_context(db_session, org_b)
    await repo.create_usage_log(**_call(org_b, model="other org's model"))

    await set_org_context(db_session, org_a)
    page = await repo.list_usage_logs(org_a, page=1, limit=2)
    assert page.pagination.total == 3
    assert len(page.data) == 2
    assert {row.model for row in page.data} <= {
        "claude-sonnet-5", "claude-fable-5-1", "claude-opus-5-5"
    }
