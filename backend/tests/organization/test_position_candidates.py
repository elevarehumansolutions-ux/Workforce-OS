"""Which positions may still be offered to the AI as critical candidates.

Scenario: Adaeze's company has Operations (critical), Finance (not critical)
and Sales (critical). Only positions that are active, not already critical,
and inside a critical department are candidates — and never another
organization's.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.organization.repository import PositionRepository

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


async def _department(client, h, name, is_critical):
    resp = await client.post(DEPARTMENTS, json={"name": name, "is_critical": is_critical}, headers=h)
    return resp.json()["id"]


async def _position(client, h, department_id, title, **extra):
    resp = await client.post(
        POSITIONS, json={"department_id": department_id, "title": title, **extra}, headers=h
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_only_active_uncritical_positions_of_critical_departments_are_candidates(
    client, db_session
):
    """Each exclusion rule is exercised: already critical, non-critical dept, soft-deleted."""
    owner = await register_verified_and_login(client, email="cand1@example.com")
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    operations = await _department(client, h, "Operations", True)
    finance = await _department(client, h, "Finance", False)
    sales = await _department(client, h, "Sales", True)

    await _position(
        client, h, operations, "Fleet Manager",
        is_critical=True, risk_level="high", criticality_type="operational",
    )
    await _position(client, h, operations, "Dispatcher")
    await _position(client, h, operations, "Driver")
    await _position(client, h, finance, "Accountant")
    await _position(client, h, sales, "Account Executive")
    retired = await _position(client, h, sales, "Retired Role")
    assert (await client.delete(f"{POSITIONS}/{retired}", headers=h)).status_code in (200, 204)
    await set_org_context(db_session, org_id)

    rows = await PositionRepository(db_session).list_candidate_positions_for_criticality(org_id)

    # Compared as a set: the shared test session gives every row the same created_at.
    assert {(department.name, position.title) for position, department in rows} == {
        ("Operations", "Dispatcher"),
        ("Operations", "Driver"),
        ("Sales", "Account Executive"),
    }


@pytest.mark.asyncio
async def test_another_organizations_positions_are_never_candidates(client, db_session):
    """Org B's critical department and position don't leak into org A's candidates."""
    owner_a = await register_verified_and_login(client, email="cand2a@example.com")
    owner_b = await register_verified_and_login(client, email="cand2b@example.com")
    ha = {"Authorization": f"Bearer {owner_a['access_token']}"}
    hb = {"Authorization": f"Bearer {owner_b['access_token']}"}
    await _position(client, ha, await _department(client, ha, "Ops", True), "Dispatcher")
    await _position(client, hb, await _department(client, hb, "Ops", True), "Secret Role")
    org_a = uuid.UUID(owner_a["organization"]["id"])
    await set_org_context(db_session, org_a)

    rows = await PositionRepository(db_session).list_candidate_positions_for_criticality(org_a)

    assert [position.title for position, _ in rows] == ["Dispatcher"]
