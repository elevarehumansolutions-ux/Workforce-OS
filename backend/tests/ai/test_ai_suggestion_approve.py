"""Repository-level tests for AISuggestionRepository.approve_pending_suggestion.

Same atomic-claim property as reject (only a still-pending suggestion, only
once, only within the caller's org), plus the approve-specific one: the AI's
suggested_* values are copied into reviewed_* by the UPDATE itself.
"""
import uuid
from decimal import Decimal

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.repository import AISuggestionRepository


async def _seed(client, db_session, email, suggestion):
    """Register an org with a department and position, then create one pending suggestion.

    ``suggestion`` is called with (org_id, department_id, position_id) and returns
    the dict to insert, so each test can shape its own target.
    """
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        "/api/v1/positions",
        json={"department_id": dept.json()["id"], "title": "General Manager"},
        headers=h,
    )
    await set_org_context(db_session, org_id)
    repo = AISuggestionRepository(db_session)
    created = await repo.create_pending_suggestion(
        suggestion(org_id, uuid.UUID(dept.json()["id"]), uuid.UUID(pos.json()["id"]))
    )
    return repo, org_id, user_id, created.id


def _critical_position(org_id, dept_id, position_id):
    return {
        "organization_id": org_id,
        "suggestion_type": "critical_position",
        "position_id": position_id,
        "suggested_criticality_type": "revenue_generating",
        "suggested_risk_level": "high",
        "rationale": "test",
    }


@pytest.mark.asyncio
async def test_approve_copies_suggested_values_into_reviewed(client, db_session):
    """Approving records who/when and copies suggested_* into reviewed_* in the same UPDATE."""
    repo, _, user_id, suggestion_id = await _seed(
        client, db_session, "ai_appr1@example.com", _critical_position
    )

    approved = await repo.approve_pending_suggestion(suggestion_id, user_id)

    assert approved is not None
    assert approved.status == "approved"
    assert approved.reviewed_by_user_id == user_id
    assert approved.reviewed_at is not None
    assert approved.reviewed_criticality_type == "revenue_generating"
    assert approved.reviewed_risk_level == "high"
    # Nothing was suggested for these, so nothing is copied.
    assert approved.reviewed_revenue_allocation_percentage is None
    assert approved.reviewed_department_name is None


@pytest.mark.asyncio
async def test_approve_copies_percentage_and_department_name(client, db_session):
    """The other suggested_* columns are copied too — verified per suggestion type."""
    repo, _, user_id, allocation_id = await _seed(
        client,
        db_session,
        "ai_appr2@example.com",
        lambda org, dept, pos: {
            "organization_id": org,
            "suggestion_type": "revenue_allocation",
            "department_id": dept,
            "suggested_revenue_allocation_percentage": Decimal("40.00"),
            "rationale": "test",
        },
    )
    approved = await repo.approve_pending_suggestion(allocation_id, user_id)
    assert approved.reviewed_revenue_allocation_percentage == Decimal("40.00")

    missing = await repo.create_pending_suggestion(
        {
            "organization_id": approved.organization_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "  Customer Success ",
            "rationale": "test",
        }
    )
    approved_missing = await repo.approve_pending_suggestion(missing.id, user_id)
    # The raw name is copied as-is — the normalized key is only for matching.
    assert approved_missing.reviewed_department_name == "  Customer Success "


@pytest.mark.asyncio
async def test_approving_twice_is_a_noop_the_second_time(client, db_session):
    """The second approve returns None and doesn't rewrite the first decision."""
    repo, _, user_id, suggestion_id = await _seed(
        client, db_session, "ai_appr3@example.com", _critical_position
    )
    first = await repo.approve_pending_suggestion(suggestion_id, user_id)

    assert await repo.approve_pending_suggestion(suggestion_id, user_id) is None
    assert (await repo.get_suggestion_by_id(suggestion_id)).reviewed_at == first.reviewed_at


@pytest.mark.asyncio
async def test_approve_and_reject_exclude_each_other(client, db_session):
    """Whichever review lands first wins; the other finds nothing pending."""
    repo, _, user_id, approved_id = await _seed(
        client, db_session, "ai_appr4@example.com", _critical_position
    )
    await repo.approve_pending_suggestion(approved_id, user_id)
    assert await repo.reject_pending_suggestion(approved_id, user_id) is None
    assert (await repo.get_suggestion_by_id(approved_id)).status == "approved"

    rejected = await repo.create_pending_suggestion(
        {
            "organization_id": (await repo.get_suggestion_by_id(approved_id)).organization_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "Legal",
            "rationale": "test",
        }
    )
    await repo.reject_pending_suggestion(rejected.id, user_id)
    assert await repo.approve_pending_suggestion(rejected.id, user_id) is None
    assert (await repo.get_suggestion_by_id(rejected.id)).status == "rejected"


@pytest.mark.asyncio
async def test_approve_unknown_or_foreign_suggestion_returns_none(client, db_session):
    """Unknown ids and another org's suggestion (RLS) both match nothing."""
    repo, org_a, _, suggestion_id = await _seed(
        client, db_session, "ai_appr5a@example.com", _critical_position
    )
    other = await register_verified_and_login(client, email="ai_appr5b@example.com")
    other_user = uuid.UUID(other["user"]["id"])

    assert await repo.approve_pending_suggestion(uuid.uuid4(), other_user) is None

    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))
    assert await repo.approve_pending_suggestion(suggestion_id, other_user) is None

    await set_org_context(db_session, org_a)
    assert (await repo.get_suggestion_by_id(suggestion_id)).status == "pending"
