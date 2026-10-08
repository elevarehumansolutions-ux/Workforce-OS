"""Repository-level tests for AISuggestionRepository.edit_pending_suggestion.

Same atomic-claim property as reject/approve, plus: the reviewer's value wins
where supplied and the AI's value fills every other slot, in the one UPDATE.
"""
import uuid
from decimal import Decimal

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.repository import AISuggestionRepository


async def _seed(client, db_session, email):
    """Register an org with a department and position; return a repo and the ids."""
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
    return (
        AISuggestionRepository(db_session),
        org_id,
        user_id,
        uuid.UUID(dept.json()["id"]),
        uuid.UUID(pos.json()["id"]),
    )


@pytest.mark.asyncio
async def test_edit_changes_only_what_the_reviewer_supplied(client, db_session):
    """A reviewer who changes only the risk level keeps the AI's criticality type."""
    repo, org_id, user_id, _, position_id = await _seed(client, db_session, "ai_edit1@example.com")
    suggestion = await repo.create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "critical_position",
            "position_id": position_id,
            "suggested_criticality_type": "revenue_generating",
            "suggested_risk_level": "high",
            "rationale": "test",
        }
    )

    edited = await repo.edit_pending_suggestion(suggestion.id, user_id, risk_level="medium")

    assert edited.status == "edited"
    assert edited.reviewed_by_user_id == user_id
    assert edited.reviewed_at is not None
    assert edited.reviewed_criticality_type == "revenue_generating"  # the AI's, untouched
    assert edited.reviewed_risk_level == "medium"  # the reviewer's
    assert edited.suggested_risk_level == "high"  # the AI's proposal is preserved


@pytest.mark.asyncio
async def test_edit_percentage_and_name(client, db_session):
    """The percentage and department-name edits work the same way."""
    repo, org_id, user_id, dept_id, _ = await _seed(client, db_session, "ai_edit2@example.com")
    allocation = await repo.create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "revenue_allocation",
            "department_id": dept_id,
            "suggested_revenue_allocation_percentage": Decimal("40.00"),
            "rationale": "test",
        }
    )
    edited = await repo.edit_pending_suggestion(
        allocation.id, user_id, revenue_allocation_percentage=Decimal("35.50")
    )
    assert edited.reviewed_revenue_allocation_percentage == Decimal("35.50")
    assert edited.suggested_revenue_allocation_percentage == Decimal("40.00")

    missing = await repo.create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "missing_department",
            "suggested_department_name": "Customer Success",
            "rationale": "test",
        }
    )
    edited_name = await repo.edit_pending_suggestion(
        missing.id, user_id, department_name="Client Success"
    )
    assert edited_name.reviewed_department_name == "Client Success"


@pytest.mark.asyncio
async def test_editing_twice_or_after_another_decision_is_a_noop(client, db_session):
    """Only a pending suggestion can be edited, once."""
    repo, org_id, user_id, _, position_id = await _seed(client, db_session, "ai_edit3@example.com")
    suggestion = await repo.create_pending_suggestion(
        {
            "organization_id": org_id,
            "suggestion_type": "critical_position",
            "position_id": position_id,
            "suggested_criticality_type": "revenue_generating",
            "suggested_risk_level": "high",
            "rationale": "test",
        }
    )
    await repo.edit_pending_suggestion(suggestion.id, user_id, risk_level="medium")

    assert await repo.edit_pending_suggestion(suggestion.id, user_id, risk_level="low") is None
    assert await repo.approve_pending_suggestion(suggestion.id, user_id) is None
    assert await repo.reject_pending_suggestion(suggestion.id, user_id) is None
    assert (await repo.get_suggestion_by_id(suggestion.id)).reviewed_risk_level == "medium"


@pytest.mark.asyncio
async def test_edit_unknown_or_foreign_suggestion_returns_none(client, db_session):
    """Unknown ids and another org's suggestion (RLS) match nothing."""
    repo, org_a, _, _, position_id = await _seed(client, db_session, "ai_edit4a@example.com")
    suggestion = await repo.create_pending_suggestion(
        {
            "organization_id": org_a,
            "suggestion_type": "critical_position",
            "position_id": position_id,
            "suggested_criticality_type": "revenue_generating",
            "suggested_risk_level": "high",
            "rationale": "test",
        }
    )
    other = await register_verified_and_login(client, email="ai_edit4b@example.com")
    other_user = uuid.UUID(other["user"]["id"])

    assert await repo.edit_pending_suggestion(uuid.uuid4(), other_user, risk_level="low") is None

    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))
    assert await repo.edit_pending_suggestion(suggestion.id, other_user, risk_level="low") is None

    await set_org_context(db_session, org_a)
    assert (await repo.get_suggestion_by_id(suggestion.id)).status == "pending"


@pytest.mark.asyncio
async def test_a_review_that_matches_nothing_leaves_the_in_memory_object_alone(client, db_session):
    """When another org's review attempt matches no row, a suggestion object we hold is not mutated.

    Guards the SQLAlchemy session-synchronization trap: without
    synchronize_session=False the ORM evaluates the WHERE in Python and can
    mark our in-memory object reviewed although the database changed nothing.
    """
    repo, org_a, _, _, position_id = await _seed(client, db_session, "ai_edit5a@example.com")
    held = await repo.create_pending_suggestion(
        {
            "organization_id": org_a,
            "suggestion_type": "critical_position",
            "position_id": position_id,
            "suggested_criticality_type": "revenue_generating",
            "suggested_risk_level": "high",
            "rationale": "test",
        }
    )
    other = await register_verified_and_login(client, email="ai_edit5b@example.com")
    other_user = uuid.UUID(other["user"]["id"])
    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))

    assert await repo.edit_pending_suggestion(held.id, other_user, risk_level="low") is None
    assert await repo.approve_pending_suggestion(held.id, other_user) is None
    assert await repo.reject_pending_suggestion(held.id, other_user) is None

    assert held.status == "pending"
    assert held.reviewed_at is None
