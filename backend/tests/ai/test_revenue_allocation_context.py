"""Gathering everything one revenue-allocation run needs.

Scenario: Kelechi's company has Operations and Sales marked critical, and
Finance is not. The gatherer hands back each critical department labelled
D1, D2..., a working handle map, and the org's capital investment amount —
and, for an org with nothing critical, nothing at all.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.ai.generation import gather_revenue_allocation_context

DEPARTMENTS = "/api/v1/departments"


async def _org(client, db_session, email):
    owner = await register_verified_and_login(client, email=email)
    h = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = uuid.UUID(owner["organization"]["id"])
    await set_org_context(db_session, org_id)
    return org_id, h


@pytest.mark.asyncio
async def test_each_critical_department_gets_a_handle_that_resolves_back_to_it(client, db_session):
    """Two critical departments, one non-critical: only the two critical ones appear."""
    org_id, h = await _org(client, db_session, "rev_ctx1@example.com")
    ops = await client.post(DEPARTMENTS, json={"name": "Operations", "is_critical": True}, headers=h)
    sales = await client.post(DEPARTMENTS, json={"name": "Sales", "is_critical": True}, headers=h)
    await client.post(DEPARTMENTS, json={"name": "Finance", "is_critical": False}, headers=h)

    context = await gather_revenue_allocation_context(db_session, org_id)

    names_by_handle = {d.handle: d.name for d in context.departments}
    assert set(names_by_handle.values()) == {"Operations", "Sales"}
    assert set(context.handles) == set(names_by_handle)
    resolved_ids = {context.handles[handle] for handle in names_by_handle}
    assert resolved_ids == {uuid.UUID(ops.json()["id"]), uuid.UUID(sales.json()["id"])}


@pytest.mark.asyncio
async def test_business_dna_including_capital_investment_is_carried_into_the_context(client, db_session):
    """The saved capital investment amount reaches the prompt inputs."""
    org_id, h = await _org(client, db_session, "rev_ctx2@example.com")
    await client.post(DEPARTMENTS, json={"name": "Operations", "is_critical": True}, headers=h)
    saved = await client.put(
        "/api/v1/business-dna",
        json={"industry": "Logistics", "capital_investment_amount": "2000000"},
        headers=h,
    )
    assert saved.status_code == 200

    context = await gather_revenue_allocation_context(db_session, org_id)

    assert context.business.industry == "Logistics"
    assert context.business.capital_investment_amount == 2_000_000


@pytest.mark.asyncio
async def test_a_department_that_already_has_a_percentage_is_still_a_candidate(client, db_session):
    """Unlike positions, an existing allocation doesn't exclude a department — it may be revisited."""
    org_id, h = await _org(client, db_session, "rev_ctx3@example.com")
    dept = await client.post(DEPARTMENTS, json={"name": "Operations", "is_critical": True}, headers=h)
    await client.patch(
        f"{DEPARTMENTS}/{dept.json()['id']}",
        json={"revenue_allocation_percentage": "40"},
        headers=h,
    )

    context = await gather_revenue_allocation_context(db_session, org_id)

    assert [d.name for d in context.departments] == ["Operations"]


@pytest.mark.asyncio
async def test_nothing_critical_means_no_context(client, db_session):
    """No critical department -> None, so the caller makes no (paid) Claude call."""
    org_id, h = await _org(client, db_session, "rev_ctx4@example.com")
    await client.post(DEPARTMENTS, json={"name": "Finance", "is_critical": False}, headers=h)

    assert await gather_revenue_allocation_context(db_session, org_id) is None
