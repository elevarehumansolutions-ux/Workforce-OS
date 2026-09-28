"""Service-level tests for editing a suggestion (a reviewer corrects the AI, then it is applied).

Scenario throughout: HR admin Adaeze reviews an AI suggestion and changes one field.
"""
import uuid
from decimal import Decimal

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.core.exceptions import (
    AlreadyExistsException,
    SuggestionAlreadyReviewedException,
    SuggestionNotFoundException,
    ValidationException,
)
from app.modules.ai.schemas import AISuggestionEditRequest
from tests.ai.test_ai_suggestion_service_approve import (
    _audit_entries,
    _department_names,
    _department_state,
    _position_state,
    _seed,
    _seed_allocation,
    _seed_missing_department,
    _suggestion_status,
)


@pytest.mark.asyncio
async def test_adaeze_changes_only_the_risk_level(client, db_session):
    """GM suggested 'revenue_generating / high'; she edits risk to medium and it's applied."""
    service, _, user_id, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_edit1@example.com"
    )

    result = await service.edit_suggestion(
        suggestion_id, user_id, AISuggestionEditRequest(risk_level="medium")
    )

    assert result.status == "edited"
    assert result.suggested_risk_level == "high"  # what the AI proposed is kept
    assert result.reviewed_risk_level == "medium"  # what Adaeze decided
    assert result.reviewed_criticality_type == "revenue_generating"  # untouched, the AI's
    assert await _position_state(db_session, position_id) == (True, "revenue_generating", "medium")

    (entry,) = await _audit_entries(db_session, "ai_suggestion", suggestion_id)
    assert entry.action == "edit"
    assert entry.changes["new"] == {"status": "edited", "risk_level": "medium"}


@pytest.mark.asyncio
async def test_editing_an_allocation_percentage_applies_it_and_audits_a_decimal(client, db_session):
    """A Decimal in the edit must survive being written to the JSON audit log."""
    service, _, user_id, department_id, suggestion_id, _ = await _seed_allocation(
        client, db_session, "ai_svc_edit2@example.com"
    )

    await service.edit_suggestion(
        suggestion_id, user_id, AISuggestionEditRequest(revenue_allocation_percentage=Decimal("35.50"))
    )

    assert await _department_state(db_session, department_id) == (False, Decimal("35.50"))
    (entry,) = await _audit_entries(db_session, "ai_suggestion", suggestion_id)
    assert entry.changes["new"]["status"] == "edited"


@pytest.mark.asyncio
async def test_editing_a_missing_department_name_creates_it_with_her_name(client, db_session):
    """AI said 'Customer Success'; Adaeze prefers 'Client Success' — that's what gets created."""
    service, org_id, user_id, suggestion_id, _ = await _seed_missing_department(
        client, db_session, "ai_svc_edit3@example.com"
    )

    await service.edit_suggestion(
        suggestion_id, user_id, AISuggestionEditRequest(department_name="Client Success")
    )

    assert await _department_names(db_session, org_id) == ["Client Success"]


@pytest.mark.asyncio
async def test_a_field_that_does_not_fit_the_type_is_refused(client, db_session):
    """A percentage on a position suggestion is a mistake — nothing changes."""
    service, _, user_id, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_edit4@example.com"
    )

    with pytest.raises(ValidationException):
        await service.edit_suggestion(
            suggestion_id, user_id, AISuggestionEditRequest(revenue_allocation_percentage=Decimal("30"))
        )

    assert await _suggestion_status(db_session, suggestion_id) == "pending"
    assert await _position_state(db_session, position_id) == (False, None, None)


@pytest.mark.asyncio
async def test_an_edit_identical_to_the_ai_is_refused_as_an_approve(client, db_session):
    """Sending 'high' when the AI said 'high' is not a correction."""
    service, _, user_id, _, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_edit5@example.com"
    )

    with pytest.raises(ValidationException):
        await service.edit_suggestion(
            suggestion_id, user_id, AISuggestionEditRequest(risk_level="high")
        )

    assert await _suggestion_status(db_session, suggestion_id) == "pending"


@pytest.mark.asyncio
async def test_unknown_and_foreign_suggestions_are_not_found(client, db_session):
    """404 for an id that doesn't exist and for another org's suggestion."""
    service, org_a, _, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_edit6a@example.com"
    )
    other = await register_verified_and_login(client, email="ai_svc_edit6b@example.com")
    other_user = uuid.UUID(other["user"]["id"])
    edit = AISuggestionEditRequest(risk_level="low")

    with pytest.raises(SuggestionNotFoundException):
        await service.edit_suggestion(uuid.uuid4(), other_user, edit)

    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))
    with pytest.raises(SuggestionNotFoundException):
        await service.edit_suggestion(suggestion_id, other_user, edit)

    await set_org_context(db_session, org_a)
    assert await _position_state(db_session, position_id) == (False, None, None)


@pytest.mark.asyncio
async def test_editing_after_another_reviewer_decided_is_a_conflict(client, db_session):
    """Someone approved it first; Adaeze's edit gets a 409 and the position keeps the approved values."""
    service, _, user_id, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_edit7@example.com"
    )
    await service.approve_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.edit_suggestion(
            suggestion_id, user_id, AISuggestionEditRequest(risk_level="low")
        )

    assert await _position_state(db_session, position_id) == (True, "revenue_generating", "high")


@pytest.mark.asyncio
async def test_a_failed_apply_undoes_the_edit(client, db_session):
    """Edited name already exists: 409, and (savepoint standing in for the router) the suggestion is pending again."""
    service, org_id, user_id, suggestion_id, headers = await _seed_missing_department(
        client, db_session, "ai_svc_edit8@example.com"
    )
    await client.post("/api/v1/departments", json={"name": "Client Success"}, headers=headers)
    await set_org_context(db_session, org_id)

    with pytest.raises(AlreadyExistsException):
        async with db_session.begin_nested():
            await service.edit_suggestion(
                suggestion_id, user_id, AISuggestionEditRequest(department_name="client   success")
            )

    assert await _suggestion_status(db_session, suggestion_id) == "pending"
    assert await _department_names(db_session, org_id) == ["Client Success"]
