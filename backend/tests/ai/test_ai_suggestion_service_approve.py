"""Service-level tests for approving a critical_position suggestion.

Approval claims the suggestion atomically, then applies it to the real
position through Org Structure's PositionService (never by writing to the
positions table directly), auditing both the position change and the
approval.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from tests.conftest import register_verified_and_login, set_org_context
from app.core.exceptions import (
    AlreadyExistsException,
    DepartmentNotFoundException,
    KPIWeightConflictException,
    PositionNotFoundException,
    SuggestionAlreadyReviewedException,
    SuggestionNotFoundException,
)
from app.modules.ai.schemas import AISuggestionCreateRequest
from app.modules.ai.service import AISuggestionService
from app.modules.audit_and_notification.models import AuditLog
from app.modules.kpis.models import KPI
from app.modules.organization.models import Department, Position


async def _seed(client, db_session, email, position_fields=None, **suggestion_fields):
    """Register an org with one position and one pending critical_position suggestion for it."""
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        "/api/v1/positions",
        json={
            "department_id": dept.json()["id"],
            "title": "General Manager",
            **(position_fields or {}),
        },
        headers=h,
    )
    position_id = uuid.UUID(pos.json()["id"])
    await set_org_context(db_session, org_id)

    service = AISuggestionService(db_session)
    fields = {
        "suggested_criticality_type": "revenue_generating",
        "suggested_risk_level": "high",
        **suggestion_fields,
    }
    created = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=position_id,
            rationale="Owns the revenue-critical function.",
            **fields,
        ),
    )
    return service, org_id, user_id, position_id, created.id, h


async def _position_state(db_session, position_id):
    row = (
        await db_session.execute(
            select(Position.is_critical, Position.criticality_type, Position.risk_level).where(
                Position.id == position_id
            )
        )
    ).one()
    return row.is_critical, row.criticality_type, row.risk_level


async def _audit_entries(db_session, entity_type, entity_id):
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
    )
    return result.scalars().all()


@pytest.mark.asyncio
async def test_approve_applies_the_suggestion_to_the_real_position(client, db_session):
    """Approving flags the position critical with the suggested type/risk, and audits both changes."""
    service, _, user_id, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_appr1@example.com"
    )
    assert await _position_state(db_session, position_id) == (False, None, None)

    result = await service.approve_suggestion(suggestion_id, user_id)

    assert result.status == "approved"
    assert result.reviewed_by_user_id == user_id
    assert await _position_state(db_session, position_id) == (True, "revenue_generating", "high")

    (approval,) = await _audit_entries(db_session, "ai_suggestion", suggestion_id)
    assert approval.action == "approve"
    assert approval.changes == {"old": {"status": "pending"}, "new": {"status": "approved"}}
    # The position's own audit trail comes from PositionService, not from us.
    position_updates = await _audit_entries(db_session, "position", position_id)
    assert any(entry.action == "update" for entry in position_updates)


@pytest.mark.asyncio
async def test_approve_overwrites_what_was_on_the_position(client, db_session):
    """Approval applies the AI's values over whatever the position already had."""
    service, _, user_id, position_id, suggestion_id, _ = await _seed(
        client,
        db_session,
        "ai_svc_appr2@example.com",
        position_fields={"risk_level": "low", "criticality_type": "operational"},
    )
    assert await _position_state(db_session, position_id) == (False, "operational", "low")

    await service.approve_suggestion(suggestion_id, user_id)

    assert await _position_state(db_session, position_id) == (True, "revenue_generating", "high")


@pytest.mark.asyncio
async def test_approving_twice_is_a_conflict(client, db_session):
    """The second approve raises the 409 exception and audits nothing new."""
    service, _, user_id, _, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_appr3@example.com"
    )
    await service.approve_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert len(await _audit_entries(db_session, "ai_suggestion", suggestion_id)) == 1


@pytest.mark.asyncio
async def test_a_rejected_suggestion_cannot_then_be_approved(client, db_session):
    """Review decisions are final: reject-then-approve is a conflict, and the position is untouched."""
    service, _, user_id, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_appr4@example.com"
    )
    await service.reject_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _position_state(db_session, position_id) == (False, None, None)


@pytest.mark.asyncio
async def test_approve_unknown_and_foreign_suggestions_are_not_found(client, db_session):
    """Unknown ids and another org's suggestion are both a 404 — nothing confirms it exists."""
    service, org_a, _, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_appr5a@example.com"
    )
    other = await register_verified_and_login(client, email="ai_svc_appr5b@example.com")
    other_user = uuid.UUID(other["user"]["id"])

    with pytest.raises(SuggestionNotFoundException):
        await service.approve_suggestion(uuid.uuid4(), other_user)

    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))
    with pytest.raises(SuggestionNotFoundException):
        await service.approve_suggestion(suggestion_id, other_user)

    await set_org_context(db_session, org_a)
    assert await _position_state(db_session, position_id) == (False, None, None)


@pytest.mark.asyncio
async def test_approving_a_suggestion_whose_position_was_deleted_fails(client, db_session):
    """The write-through raises NotFound for a deleted target.

    The API can no longer produce this state — deleting a position with a
    pending suggestion is blocked (08_DECISIONS.md 2026-09-24) — so it's
    simulated with a direct soft-delete, standing in for the race where a
    delete lands between a suggestion being created and reviewed. In a real
    request the router's transaction then rolls back, leaving the suggestion
    pending.
    """
    service, org_id, user_id, position_id, suggestion_id, _ = await _seed(
        client, db_session, "ai_svc_appr6@example.com"
    )
    await db_session.execute(
        update(Position).where(Position.id == position_id).values(deleted_at=datetime.now(UTC))
    )

    with pytest.raises(PositionNotFoundException):
        await service.approve_suggestion(suggestion_id, user_id)


async def _seed_allocation(client, db_session, email, percentage="40.00"):
    """Register an org with one department and one pending revenue_allocation suggestion for it."""
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    dept = await client.post("/api/v1/departments", json={"name": "Operations"}, headers=h)
    department_id = uuid.UUID(dept.json()["id"])
    await set_org_context(db_session, org_id)

    service = AISuggestionService(db_session)
    created = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="revenue_allocation",
            department_id=department_id,
            suggested_revenue_allocation_percentage=Decimal(percentage),
            rationale="Primary revenue driver.",
        ),
    )
    return service, org_id, user_id, department_id, created.id, h


async def _department_state(db_session, department_id):
    row = (
        await db_session.execute(
            select(Department.is_critical, Department.revenue_allocation_percentage).where(
                Department.id == department_id
            )
        )
    ).one()
    return row.is_critical, row.revenue_allocation_percentage


@pytest.mark.asyncio
async def test_approve_allocation_sets_the_departments_percentage(client, db_session):
    """Approving applies the exact percentage to the department and audits both changes.

    The department here is *not* critical, and approval still applies the
    percentage without touching is_critical — the noted edge case in
    08_DECISIONS.md 2026-09-24 (apply anyway, consistent with what
    update_department already allows manually).
    """
    service, _, user_id, department_id, suggestion_id, _ = await _seed_allocation(
        client, db_session, "ai_svc_alloc1@example.com"
    )
    assert await _department_state(db_session, department_id) == (False, None)

    result = await service.approve_suggestion(suggestion_id, user_id)

    assert result.status == "approved"
    assert result.reviewed_revenue_allocation_percentage == Decimal("40.00")
    assert await _department_state(db_session, department_id) == (False, Decimal("40.00"))

    (approval,) = await _audit_entries(db_session, "ai_suggestion", suggestion_id)
    assert approval.action == "approve"
    department_updates = await _audit_entries(db_session, "department", department_id)
    assert any(entry.action == "update" for entry in department_updates)


@pytest.mark.asyncio
async def test_approve_allocation_twice_is_a_conflict(client, db_session):
    """The second approve is a 409 and leaves the department as the first one set it."""
    service, _, user_id, department_id, suggestion_id, _ = await _seed_allocation(
        client, db_session, "ai_svc_alloc2@example.com"
    )
    await service.approve_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _department_state(db_session, department_id) == (False, Decimal("40.00"))
    assert len(await _audit_entries(db_session, "ai_suggestion", suggestion_id)) == 1


@pytest.mark.asyncio
async def test_rejected_allocation_cannot_be_approved_and_department_is_untouched(client, db_session):
    """Reject-then-approve is a conflict, and nothing reaches the department."""
    service, _, user_id, department_id, suggestion_id, _ = await _seed_allocation(
        client, db_session, "ai_svc_alloc3@example.com"
    )
    await service.reject_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _department_state(db_session, department_id) == (False, None)


@pytest.mark.asyncio
async def test_approving_an_allocation_for_a_deleted_department_fails(client, db_session):
    """The write-through raises NotFound for a deleted department (a real request would roll back).

    Simulated with a direct soft-delete: the API now blocks deleting a
    department with a pending suggestion (08_DECISIONS.md 2026-09-24).
    """
    service, org_id, user_id, department_id, suggestion_id, _ = await _seed_allocation(
        client, db_session, "ai_svc_alloc4@example.com"
    )
    await db_session.execute(
        update(Department).where(Department.id == department_id).values(deleted_at=datetime.now(UTC))
    )

    with pytest.raises(DepartmentNotFoundException):
        await service.approve_suggestion(suggestion_id, user_id)


async def _seed_missing_department(client, db_session, email, name="Customer Success"):
    """Register an org and create one pending missing_department suggestion in it."""
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    await set_org_context(db_session, org_id)

    service = AISuggestionService(db_session)
    created = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="missing_department",
            suggested_department_name=name,
            rationale="No department owns post-sale retention.",
        ),
    )
    return service, org_id, user_id, created.id, h


async def _department_names(db_session, org_id):
    result = await db_session.execute(
        select(Department.name).where(
            Department.organization_id == org_id, Department.deleted_at.is_(None)
        )
    )
    return sorted(result.scalars().all())


async def _suggestion_status(db_session, suggestion_id):
    from app.modules.ai.models import AISuggestion

    return await db_session.scalar(
        select(AISuggestion.status).where(AISuggestion.id == suggestion_id)
    )


@pytest.mark.asyncio
async def test_approve_missing_department_creates_it(client, db_session):
    """Approving creates a real department with the approved name, and audits both changes."""
    service, org_id, user_id, suggestion_id, _ = await _seed_missing_department(
        client, db_session, "ai_svc_miss1@example.com"
    )
    assert await _department_names(db_session, org_id) == []

    result = await service.approve_suggestion(suggestion_id, user_id)

    assert result.status == "approved"
    assert result.reviewed_department_name == "Customer Success"
    assert await _department_names(db_session, org_id) == ["Customer Success"]
    # It's created as a plain, non-critical department — the AI proposed a
    # missing department, not its criticality or allocation.
    is_critical = await db_session.scalar(
        select(Department.is_critical).where(Department.organization_id == org_id)
    )
    assert is_critical is False

    (approval,) = await _audit_entries(db_session, "ai_suggestion", suggestion_id)
    assert approval.action == "approve"
    created_id = await db_session.scalar(
        select(Department.id).where(Department.organization_id == org_id)
    )
    department_entries = await _audit_entries(db_session, "department", created_id)
    assert any(entry.action == "create" for entry in department_entries)


@pytest.mark.asyncio
async def test_approve_missing_department_fails_if_the_name_now_exists(client, db_session):
    """A name HR created by hand since the suggestion was made is a 409 — and nothing is left half-done.

    A SAVEPOINT stands in for the router's rollback, so this proves the
    claim on the suggestion is undone with the failed approval: it goes
    back to pending, and no second department exists.
    """
    service, org_id, user_id, suggestion_id, headers = await _seed_missing_department(
        client, db_session, "ai_svc_miss2@example.com"
    )
    made_by_hand = await client.post(
        "/api/v1/departments", json={"name": "  customer   SUCCESS "}, headers=headers
    )
    assert made_by_hand.status_code == 200
    await set_org_context(db_session, org_id)

    with pytest.raises(AlreadyExistsException):
        async with db_session.begin_nested():
            await service.approve_suggestion(suggestion_id, user_id)

    assert await _suggestion_status(db_session, suggestion_id) == "pending"
    assert len(await _department_names(db_session, org_id)) == 1
    assert await _audit_entries(db_session, "ai_suggestion", suggestion_id) == []


@pytest.mark.asyncio
async def test_approve_missing_department_twice_creates_only_one(client, db_session):
    """The second approve is a 409 and doesn't create a second department."""
    service, org_id, user_id, suggestion_id, _ = await _seed_missing_department(
        client, db_session, "ai_svc_miss3@example.com"
    )
    await service.approve_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _department_names(db_session, org_id) == ["Customer Success"]


@pytest.mark.asyncio
async def test_rejected_missing_department_cannot_be_approved(client, db_session):
    """Reject-then-approve is a conflict and creates nothing."""
    service, org_id, user_id, suggestion_id, _ = await _seed_missing_department(
        client, db_session, "ai_svc_miss4@example.com"
    )
    await service.reject_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _department_names(db_session, org_id) == []


async def _seed_kpi_weight(client, db_session, email, weight="40.00", second_kpi_weight="60.00"):
    """Register an org with two KPIs (summing to 100) and a pending kpi_weight suggestion for the first."""
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    user_id = uuid.UUID(owner["user"]["id"])
    dept = await client.post("/api/v1/departments", json={"name": "Sales"}, headers=h)
    department_id = dept.json()["id"]
    k1 = await client.post(
        "/api/v1/kpis",
        json={"department_id": department_id, "name": "Deals closed", "weight": "30.00"},
        headers=h,
    )
    await client.post(
        "/api/v1/kpis",
        json={"department_id": department_id, "name": "Pipeline value", "weight": second_kpi_weight},
        headers=h,
    )
    kpi_id = uuid.UUID(k1.json()["id"])
    await set_org_context(db_session, org_id)

    service = AISuggestionService(db_session)
    created = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="kpi_weight",
            kpi_id=kpi_id,
            suggested_weight=Decimal(weight),
            rationale="Core revenue driver for this team.",
        ),
    )
    return service, org_id, user_id, kpi_id, created.id


async def _kpi_weight(db_session, kpi_id):
    return await db_session.scalar(select(KPI.weight).where(KPI.id == kpi_id))


@pytest.mark.asyncio
async def test_approve_kpi_weight_rejects_a_suggestion_that_would_exceed_100(client, db_session):
    """Approving reuses KPIService's own weight-sum validation — it's not a bypass.

    The group starts at 30 (first KPI) + 60 (second) = 90. The suggestion
    proposes 50 for the first KPI, which would make the group
    50 + 60 = 110 — over the cap, so it must be rejected, the same as if
    someone had PATCHed that weight directly.
    """
    service, _, user_id, kpi_id, suggestion_id = await _seed_kpi_weight(
        client, db_session, "ai_svc_kw1@example.com", weight="50.00"
    )
    assert await _kpi_weight(db_session, kpi_id) == Decimal("30.00")

    with pytest.raises(KPIWeightConflictException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _kpi_weight(db_session, kpi_id) == Decimal("30.00")


@pytest.mark.asyncio
async def test_approve_kpi_weight_within_the_groups_room_succeeds(client, db_session):
    """A suggestion that doesn't push the group over 100 applies cleanly."""
    service, _, user_id, kpi_id, suggestion_id = await _seed_kpi_weight(
        client, db_session, "ai_svc_kw2@example.com", weight="20.00", second_kpi_weight="60.00"
    )

    result = await service.approve_suggestion(suggestion_id, user_id)

    assert result.status == "approved"
    assert result.reviewed_weight == Decimal("20.00")
    assert await _kpi_weight(db_session, kpi_id) == Decimal("20.00")

    (approval,) = await _audit_entries(db_session, "ai_suggestion", suggestion_id)
    assert approval.action == "approve"
    kpi_updates = await _audit_entries(db_session, "kpi", kpi_id)
    assert any(entry.action == "update" for entry in kpi_updates)


@pytest.mark.asyncio
async def test_approve_kpi_weight_twice_is_a_conflict(client, db_session):
    """The second approve is a 409 and the KPI keeps its first-approved weight."""
    service, _, user_id, kpi_id, suggestion_id = await _seed_kpi_weight(
        client, db_session, "ai_svc_kw3@example.com", weight="35.00", second_kpi_weight="65.00"
    )
    await service.approve_suggestion(suggestion_id, user_id)
    assert await _kpi_weight(db_session, kpi_id) == Decimal("35.00")

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _kpi_weight(db_session, kpi_id) == Decimal("35.00")


@pytest.mark.asyncio
async def test_rejected_kpi_weight_cannot_be_approved_and_kpi_is_untouched(client, db_session):
    """Reject-then-approve is a conflict and the KPI's weight never changes."""
    service, _, user_id, kpi_id, suggestion_id = await _seed_kpi_weight(
        client, db_session, "ai_svc_kw4@example.com", weight="35.00", second_kpi_weight="65.00"
    )
    await service.reject_suggestion(suggestion_id, user_id)

    with pytest.raises(SuggestionAlreadyReviewedException):
        await service.approve_suggestion(suggestion_id, user_id)

    assert await _kpi_weight(db_session, kpi_id) == Decimal("30.00")
