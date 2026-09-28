"""Service-level tests for AISuggestionService.create_suggestion_if_eligible.

Covers the two idempotency rules working together: the pending-duplicate
no-op (database enforced) and the rejected-suggestion quarterly
suppression (08_DECISIONS.md 2026-09-22), including that a rejection from
a *previous* fiscal quarter no longer blocks.
"""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update

from tests.conftest import register_verified_and_login, set_org_context
from app.core.exceptions import OrganizationNotFoundException
from app.core.fiscal import get_fiscal_quarter_start
from app.modules.ai.models import AISuggestion
from app.modules.ai.schemas import AISuggestionCreateRequest
from app.modules.ai.repository import AISuggestionRepository
from app.modules.ai.service import AISuggestionService
from app.modules.tenancy_identity.models import Membership

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


async def _seed(client, db_session, email):
    """Register an org with one department and one position; return ids and a ready service."""
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "GM"}, headers=h
    )
    await set_org_context(db_session, org_id)
    return org_id, uuid.UUID(dept.json()["id"]), uuid.UUID(pos.json()["id"]), AISuggestionService(db_session)


def _missing_department(name="Customer Success"):
    return AISuggestionCreateRequest(
        suggestion_type="missing_department",
        suggested_department_name=name,
        rationale="No department owns post-sale retention.",
    )


async def _reject_for_real(db_session, org_id, suggestion_id):
    """Reject through the real repository method, as a reviewer in the org would."""
    reviewer_id = await db_session.scalar(
        select(Membership.user_id).where(Membership.organization_id == org_id)
    )
    return await AISuggestionRepository(db_session).reject_pending_suggestion(
        suggestion_id, reviewer_id
    )


async def _reject_at(db_session, suggestion_id, reviewed_at):
    """Backdate a rejection with a raw UPDATE — the real method always stamps 'now'."""
    await db_session.execute(
        update(AISuggestion)
        .where(AISuggestion.id == suggestion_id)
        .values(status="rejected", reviewed_at=reviewed_at)
    )


async def _row_count(db_session, org_id):
    return await db_session.scalar(
        select(func.count()).select_from(AISuggestion).where(AISuggestion.organization_id == org_id)
    )


@pytest.mark.asyncio
async def test_creates_pending_suggestion_when_eligible(client, db_session):
    """A fresh candidate is persisted as pending and returned as a response."""
    org_id, _, _, service = await _seed(client, db_session, "ai_svc1@example.com")

    result = await service.create_suggestion_if_eligible(org_id, _missing_department())

    assert result is not None
    assert result.status == "pending"
    assert result.organization_id == org_id
    assert result.suggested_department_name == "Customer Success"


@pytest.mark.asyncio
async def test_duplicate_pending_is_a_quiet_noop(client, db_session):
    """A retried/repeated candidate returns None and creates no second row."""
    org_id, _, _, service = await _seed(client, db_session, "ai_svc2@example.com")

    first = await service.create_suggestion_if_eligible(org_id, _missing_department())
    second = await service.create_suggestion_if_eligible(org_id, _missing_department())

    assert first is not None
    assert second is None
    assert await _row_count(db_session, org_id) == 1


@pytest.mark.asyncio
async def test_rejection_this_quarter_suppresses_regeneration(client, db_session):
    """After HR rejects a suggestion, the same target isn't proposed again this quarter."""
    org_id, _, _, service = await _seed(client, db_session, "ai_svc3@example.com")

    created = await service.create_suggestion_if_eligible(org_id, _missing_department())
    await _reject_for_real(db_session, org_id, created.id)

    again = await service.create_suggestion_if_eligible(org_id, _missing_department())

    assert again is None
    assert await _row_count(db_session, org_id) == 1


@pytest.mark.asyncio
async def test_rejection_variant_of_name_is_also_suppressed(client, db_session):
    """Formatting variants of a rejected name don't slip past the suppression."""
    org_id, _, _, service = await _seed(client, db_session, "ai_svc4@example.com")

    created = await service.create_suggestion_if_eligible(org_id, _missing_department())
    await _reject_for_real(db_session, org_id, created.id)

    again = await service.create_suggestion_if_eligible(
        org_id, _missing_department("  customer   SUCCESS ")
    )

    assert again is None


@pytest.mark.asyncio
async def test_rejection_from_previous_quarter_no_longer_blocks(client, db_session):
    """Once a new fiscal quarter starts, a past rejection lets the target resurface."""
    org_id, _, _, service = await _seed(client, db_session, "ai_svc5@example.com")

    created = await service.create_suggestion_if_eligible(org_id, _missing_department())
    # New orgs default to fiscal_year_start_month=1 (calendar quarters).
    last_quarter = get_fiscal_quarter_start(1, datetime.now(UTC)) - timedelta(days=1)
    await _reject_at(db_session, created.id, last_quarter)

    again = await service.create_suggestion_if_eligible(org_id, _missing_department())

    assert again is not None
    assert again.status == "pending"
    assert await _row_count(db_session, org_id) == 2


@pytest.mark.asyncio
async def test_revenue_allocation_percentage_round_trips_as_decimal(client, db_session):
    """A Decimal percentage survives create -> ORM -> response (was a str field before)."""
    org_id, dept_id, _, service = await _seed(client, db_session, "ai_svc6@example.com")

    result = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="revenue_allocation",
            department_id=dept_id,
            suggested_revenue_allocation_percentage=Decimal("40.00"),
            rationale="Primary revenue driver.",
        ),
    )

    assert result is not None
    assert result.suggested_revenue_allocation_percentage == Decimal("40.00")


@pytest.mark.asyncio
async def test_critical_position_suggestion_is_created(client, db_session):
    """A critical_position candidate persists with its position target and enum-valued fields."""
    org_id, _, position_id, service = await _seed(client, db_session, "ai_svc7@example.com")

    result = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=position_id,
            suggested_criticality_type="revenue_generating",
            suggested_risk_level="high",
            rationale="Owns the revenue-critical function.",
        ),
    )

    assert result is not None
    assert result.position_id == position_id
    assert result.suggested_risk_level == "high"


@pytest.mark.asyncio
async def test_unknown_organization_raises(client, db_session):
    """An org id not visible under the current tenant context is a NotFound, not a crash."""
    _, _, _, service = await _seed(client, db_session, "ai_svc8@example.com")

    with pytest.raises(OrganizationNotFoundException):
        await service.create_suggestion_if_eligible(uuid.uuid4(), _missing_department())


def test_candidate_missing_its_target_is_rejected_before_the_database():
    """The schema enforces the type-to-target pairing so a bad candidate can't abort a batch."""
    with pytest.raises(ValidationError):
        AISuggestionCreateRequest(suggestion_type="critical_position", rationale="no position")
    with pytest.raises(ValidationError):
        AISuggestionCreateRequest(suggestion_type="missing_department", rationale="no name")


def test_candidate_with_invalid_enum_values_is_rejected():
    """An LLM-invented risk level is caught at the boundary, not when HR later approves it."""
    with pytest.raises(ValidationError):
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=uuid.uuid4(),
            suggested_risk_level="extremely spicy",
            rationale="x",
        )


@pytest.mark.parametrize(
    "missing",
    [
        {"suggested_risk_level": "high"},  # no criticality_type
        {"suggested_criticality_type": "revenue_generating"},  # no risk_level
        {},  # neither
    ],
)
def test_critical_position_requires_both_criticality_type_and_risk_level(missing):
    """Approving a critical_position without both would flag a position critical with no description."""
    with pytest.raises(ValidationError):
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=uuid.uuid4(),
            rationale="x",
            **missing,
        )


def test_revenue_allocation_requires_its_percentage():
    """An allocation suggestion with no percentage would apply nothing to the department."""
    with pytest.raises(ValidationError):
        AISuggestionCreateRequest(
            suggestion_type="revenue_allocation",
            department_id=uuid.uuid4(),
            rationale="x",
        )
