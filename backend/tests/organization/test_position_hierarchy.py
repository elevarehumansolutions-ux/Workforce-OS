"""HTTP-level tests for validating ``positions.reports_to_position_id``.

A position may report to another position of the same organization (any
department), never to itself, never in a loop, and never into another
organization's data (08_DECISIONS.md, 09_PROGRESS.md M4 gap of 2026-10-04).
"""
import uuid

import pytest
from sqlalchemy import update

from app.modules.organization.models import Position
from tests.conftest import register_verified_and_login, set_org_context

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org(client, email: str) -> tuple[dict, dict, str]:
    """An org owner and one department."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    dept = (await client.post(DEPARTMENTS, json={"name": "Executive"}, headers=h)).json()["id"]
    return owner, h, dept


async def _position(client, h, department_id: str, title: str, reports_to: str | None = None):
    body = {"department_id": department_id, "title": title}
    if reports_to is not None:
        body["reports_to_position_id"] = reports_to
    return await client.post(POSITIONS, json=body, headers=h)


async def _reports_to(client, h, position_id: str, parent_id: str | None):
    return await client.patch(
        f"{POSITIONS}/{position_id}", json={"reports_to_position_id": parent_id}, headers=h
    )


@pytest.mark.asyncio
async def test_a_position_can_report_to_another_in_the_same_org_even_in_another_department(client):
    """The CTO in Technology reports to the CEO in Executive."""
    owner, h, executive = await _org(client, "ph_owner1@example.com")
    technology = (await client.post(DEPARTMENTS, json={"name": "Technology"}, headers=h)).json()["id"]
    ceo = (await _position(client, h, executive, "CEO")).json()["id"]

    cto = await _position(client, h, technology, "CTO", reports_to=ceo)

    assert cto.status_code == 200
    assert cto.json()["reports_to_position_id"] == ceo


@pytest.mark.asyncio
async def test_a_parent_from_another_organization_or_that_does_not_exist_is_refused(client):
    """The database's foreign key would accept these ids; the service must not."""
    owner, h, dept = await _org(client, "ph_owner2@example.com")
    other_owner, other_h, other_dept = await _org(client, "ph_other2@example.com")
    foreign = (await _position(client, other_h, other_dept, "Foreign CEO")).json()["id"]
    mine = (await _position(client, h, dept, "Officer")).json()["id"]

    on_create_foreign = await _position(client, h, dept, "Manager", reports_to=foreign)
    on_create_unknown = await _position(client, h, dept, "Manager", reports_to=str(uuid.uuid4()))
    on_update_foreign = await _reports_to(client, h, mine, foreign)

    for resp in (on_create_foreign, on_create_unknown, on_update_foreign):
        assert resp.status_code == 404
        assert resp.json()["code"] == "POSITION_NOT_FOUND"
        assert "report to" in resp.json()["message"]
    assert (await client.get(f"{POSITIONS}/{mine}", headers=h)).json()["reports_to_position_id"] is None


@pytest.mark.asyncio
async def test_a_deleted_position_cannot_be_a_parent(client):
    """Soft-deleted positions are treated as gone."""
    owner, h, dept = await _org(client, "ph_owner3@example.com")
    old = (await _position(client, h, dept, "Retired role")).json()["id"]
    assert (await client.delete(f"{POSITIONS}/{old}", headers=h)).status_code == 200

    resp = await _position(client, h, dept, "Officer", reports_to=old)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_a_position_cannot_report_to_itself(client):
    """A to A is refused with a clear 422."""
    owner, h, dept = await _org(client, "ph_owner4@example.com")
    a = (await _position(client, h, dept, "A")).json()["id"]

    resp = await _reports_to(client, h, a, a)

    assert resp.status_code == 422
    assert "itself" in resp.json()["message"]


@pytest.mark.asyncio
async def test_two_positions_cannot_report_to_each_other(client):
    """B reports to A, then A to B would be a ring of two."""
    owner, h, dept = await _org(client, "ph_owner5@example.com")
    a = (await _position(client, h, dept, "A")).json()["id"]
    b = (await _position(client, h, dept, "B", reports_to=a)).json()["id"]

    resp = await _reports_to(client, h, a, b)

    assert resp.status_code == 422
    assert "loop" in resp.json()["message"]
    assert (await client.get(f"{POSITIONS}/{a}", headers=h)).json()["reports_to_position_id"] is None


@pytest.mark.asyncio
async def test_a_longer_ring_is_refused_too(client):
    """C reports to B, B to A; making A report to C closes a ring of three."""
    owner, h, dept = await _org(client, "ph_owner6@example.com")
    a = (await _position(client, h, dept, "A")).json()["id"]
    b = (await _position(client, h, dept, "B", reports_to=a)).json()["id"]
    c = (await _position(client, h, dept, "C", reports_to=b)).json()["id"]

    resp = await _reports_to(client, h, a, c)

    assert resp.status_code == 422
    assert "loop" in resp.json()["message"]


@pytest.mark.asyncio
async def test_valid_reparenting_clearing_and_unrelated_edits_still_work(client):
    """Moving a branch, removing the parent, and renaming are all fine."""
    owner, h, dept = await _org(client, "ph_owner7@example.com")
    a = (await _position(client, h, dept, "A")).json()["id"]
    b = (await _position(client, h, dept, "B", reports_to=a)).json()["id"]
    c = (await _position(client, h, dept, "C", reports_to=b)).json()["id"]

    moved = await _reports_to(client, h, c, a)          # C now reports to A directly
    renamed = await client.patch(f"{POSITIONS}/{c}", json={"title": "C2"}, headers=h)
    cleared = await _reports_to(client, h, c, None)     # and then to nobody

    assert moved.status_code == 200 and moved.json()["reports_to_position_id"] == a
    assert renamed.status_code == 200 and renamed.json()["reports_to_position_id"] == a
    assert cleared.status_code == 200 and cleared.json()["reports_to_position_id"] is None


@pytest.mark.asyncio
async def test_an_existing_ring_elsewhere_in_the_data_does_not_hang_the_check(client, db_session):
    """Old bad data (a ring that doesn't include the edited position) ends the walk instead of looping forever."""
    owner, h, dept = await _org(client, "ph_owner8@example.com")
    org_id = owner["organization"]["id"]
    a = (await _position(client, h, dept, "A")).json()["id"]
    b = (await _position(client, h, dept, "B", reports_to=a)).json()["id"]
    c = (await _position(client, h, dept, "C")).json()["id"]
    await set_org_context(db_session, org_id)
    # Force a ring A <-> B straight into the table, bypassing the API's check.
    await db_session.execute(update(Position).where(Position.id == uuid.UUID(a)).values(reports_to_position_id=uuid.UUID(b)))
    await db_session.flush()

    resp = await _reports_to(client, h, c, a)

    assert resp.status_code == 200
