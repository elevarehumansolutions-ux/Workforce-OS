"""Gathering everything one critical-position run needs.

Scenario: Adaeze's company has Operations and Sales marked critical (and
Finance not). The gatherer must hand back labelled positions grouped by
department, a map from each label to its real position, the Business DNA,
and — for an org with nothing to ask about — nothing, so no Claude call is
made.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.generation import gather_critical_position_context

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


async def _department(client, h, name, is_critical=True):
    resp = await client.post(DEPARTMENTS, json={"name": name, "is_critical": is_critical}, headers=h)
    return resp.json()["id"]


async def _position(client, h, department_id, title):
    resp = await client.post(POSITIONS, json={"department_id": department_id, "title": title}, headers=h)
    return resp.json()["id"]


async def _org(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    return org_id, {"Authorization": f"Bearer {owner['access_token']}"}


@pytest.mark.asyncio
async def test_positions_are_grouped_by_department_with_a_working_handle_map(client, db_session):
    """Each department keeps its own positions; every handle leads to the right real position."""
    org_id, h = await _org(client, db_session, "gen_ctx1@example.com")
    operations = await _department(client, h, "Operations")
    sales = await _department(client, h, "Sales")
    dispatcher = await _position(client, h, operations, "Dispatcher")
    driver = await _position(client, h, operations, "Driver")
    executive = await _position(client, h, sales, "Account Executive")

    context = await gather_critical_position_context(db_session, org_id)

    # Grouping: two departments, each with only its own positions (guards against
    # every department accidentally receiving the last one's list).
    titles_by_department = {
        d.name: sorted(p.title for p in d.positions) for d in context.departments
    }
    assert titles_by_department == {
        "Operations": ["Dispatcher", "Driver"],
        "Sales": ["Account Executive"],
    }
    # Handles: three positions -> P1..P3, unique, each pointing at a real position.
    assert sorted(context.handles) == ["P1", "P2", "P3"]
    assert set(context.handles.values()) == {
        uuid.UUID(dispatcher),
        uuid.UUID(driver),
        uuid.UUID(executive),
    }
    # The prompt's handle labels agree with the map.
    for department in context.departments:
        for position in department.positions:
            assert position.handle in context.handles
    # Every position knows its department.
    assert context.department_of == {
        uuid.UUID(dispatcher): uuid.UUID(operations),
        uuid.UUID(driver): uuid.UUID(operations),
        uuid.UUID(executive): uuid.UUID(sales),
    }


@pytest.mark.asyncio
async def test_business_dna_is_carried_into_the_context(client, db_session):
    """The saved Business DNA fields reach the prompt inputs."""
    org_id, h = await _org(client, db_session, "gen_ctx2@example.com")
    await _position(client, h, await _department(client, h, "Operations"), "Dispatcher")
    saved = await client.put(
        "/api/v1/business-dna",
        json={"industry": "Logistics", "revenue_drivers": "Delivery contracts"},
        headers=h,
    )
    assert saved.status_code == 200

    context = await gather_critical_position_context(db_session, org_id)

    assert context.business.industry == "Logistics"
    assert context.business.revenue_drivers == "Delivery contracts"


@pytest.mark.asyncio
async def test_an_org_without_business_dna_still_gets_a_context(client, db_session):
    """Skipping Business DNA doesn't block a run; the business context is just empty."""
    org_id, h = await _org(client, db_session, "gen_ctx3@example.com")
    await _position(client, h, await _department(client, h, "Operations"), "Dispatcher")

    context = await gather_critical_position_context(db_session, org_id)

    assert context is not None
    assert context.business.industry is None


@pytest.mark.asyncio
async def test_nothing_to_ask_about_means_no_context(client, db_session):
    """No critical department -> None, so the caller makes no (paid) Claude call."""
    org_id, h = await _org(client, db_session, "gen_ctx4@example.com")
    await _position(client, h, await _department(client, h, "Finance", is_critical=False), "Accountant")

    assert await gather_critical_position_context(db_session, org_id) is None
