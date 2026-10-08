"""The kpi_weight candidate query: which department/location groups qualify.

Scenario: Sales has two KPIs (a real group to re-split); Ops has only one
(nothing to split); a Lagos-scoped group is kept separate from Sales'
department-wide one even though they share a department.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from app.modules.kpis.repository import KPIRepository

KPIS = "/api/v1/kpis"
DEPARTMENTS = "/api/v1/departments"
LOCATIONS = "/api/v1/locations"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_a_group_with_two_or_more_kpis_is_a_candidate(client, db_session):
    """Sales has two KPIs: it qualifies."""
    owner = await register_verified_and_login(client, email="cand_kw1@example.com")
    h = _h(owner["access_token"])
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    dept_id = dept.json()["id"]
    await client.post(KPIS, json={"department_id": dept_id, "name": "A", "weight": 50}, headers=h)
    await client.post(KPIS, json={"department_id": dept_id, "name": "B", "weight": 50}, headers=h)

    groups = await KPIRepository(db_session).list_candidate_kpi_groups_for_weight_suggestion(org_id)

    assert groups == [(uuid.UUID(dept_id), "Sales", None)]


@pytest.mark.asyncio
async def test_a_group_with_only_one_kpi_is_not_a_candidate(client, db_session):
    """Ops has one KPI: nothing to split, not a candidate."""
    owner = await register_verified_and_login(client, email="cand_kw2@example.com")
    h = _h(owner["access_token"])
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    await client.post(KPIS, json={"department_id": dept.json()["id"], "name": "Only one", "weight": 100}, headers=h)

    groups = await KPIRepository(db_session).list_candidate_kpi_groups_for_weight_suggestion(org_id)

    assert groups == []


@pytest.mark.asyncio
async def test_a_location_scoped_group_is_separate_from_the_department_wide_one(client, db_session):
    """Sales (dept-wide, 2 KPIs) and Sales-in-Lagos (2 KPIs) are two distinct candidates."""
    owner = await register_verified_and_login(client, email="cand_kw3@example.com")
    h = _h(owner["access_token"])
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    dept_id = dept.json()["id"]
    loc = await client.post(LOCATIONS, json={"name": "Lagos HQ"}, headers=h)
    loc_id = loc.json()["id"]

    await client.post(KPIS, json={"department_id": dept_id, "name": "A", "weight": 50}, headers=h)
    await client.post(KPIS, json={"department_id": dept_id, "name": "B", "weight": 50}, headers=h)
    await client.post(
        KPIS, json={"department_id": dept_id, "location_id": loc_id, "name": "C", "weight": 50}, headers=h
    )
    await client.post(
        KPIS, json={"department_id": dept_id, "location_id": loc_id, "name": "D", "weight": 50}, headers=h
    )

    groups = await KPIRepository(db_session).list_candidate_kpi_groups_for_weight_suggestion(org_id)

    assert {(g[0], g[2]) for g in groups} == {
        (uuid.UUID(dept_id), None),
        (uuid.UUID(dept_id), uuid.UUID(loc_id)),
    }


@pytest.mark.asyncio
async def test_candidate_groups_are_org_scoped(client, db_session):
    """Another organization's qualifying group never appears."""
    owner_a = await register_verified_and_login(client, email="cand_kw4a@example.com")
    owner_b = await register_verified_and_login(client, email="cand_kw4b@example.com")
    h_b = _h(owner_b["access_token"])
    org_a = uuid.UUID(owner_a["organization"]["id"])
    dept_b = await client.post(DEPARTMENTS, json={"name": "Other org dept"}, headers=h_b)
    await client.post(KPIS, json={"department_id": dept_b.json()["id"], "name": "A", "weight": 50}, headers=h_b)
    await client.post(KPIS, json={"department_id": dept_b.json()["id"], "name": "B", "weight": 50}, headers=h_b)

    await set_org_context(db_session, org_a)
    groups = await KPIRepository(db_session).list_candidate_kpi_groups_for_weight_suggestion(org_a)

    assert groups == []
