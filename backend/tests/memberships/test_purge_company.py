"""Erasing a deleted company for good, 30 days after it was deleted (08_DECISIONS.md 2026-11-14).

Scenario: Chidi deleted "Zenith Foods" a month ago and never restored it. The nightly job erases it and
everything in it. His other company and his own account are left alone.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.auth.purge import (
    PURGE_AFTER_DAYS,
    list_due_for_purge,
    order_for_deletion,
    purge_company,
    tables_to_purge,
)
from tests.conftest import register_verified_and_login, set_org_context
from tests.memberships.join_helper import AUTH, DEFAULT_PASSWORD

CREATE = f"{AUTH}/create-organization"
DELETE = f"{AUTH}/delete-organization"
DELETED = f"{AUTH}/deleted-organizations"
DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"


def _h(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _add_people(client, login: dict, department_name: str) -> str:
    """A department, a role and two employees, one of them head. Returns the department id."""
    h = _h(login)
    department = (await client.post(DEPARTMENTS, json={"name": department_name}, headers=h)).json()["id"]
    position = (await client.post(POSITIONS, json={"department_id": department, "title": "Officer"}, headers=h)).json()["id"]
    ids = []
    for first in ("Tunde", "Ada"):
        created = await client.post(
            EMPLOYEES,
            json={
                "position_id": position,
                "first_name": first,
                "last_name": "Test",
                "work_email": f"{first.lower()}.{uuid.uuid4().hex[:6]}@example.com",
                "start_date": "2026-01-01",
            },
            headers=h,
        )
        assert created.status_code in (200, 201), created.text
        ids.append(created.json()["id"])
    # Naming a head makes the department point at an employee, who points at a role in the department:
    # the one loop the purge has to break.
    headed = await client.patch(f"{DEPARTMENTS}/{department}", json={"head_employee_id": ids[0]}, headers=h)
    assert headed.status_code == 200, headed.text
    return department


async def _two_companies_with_people(client, email: str):
    first = await register_verified_and_login(client, email=email)
    first_department = await _add_people(client, first, "Dispatch")
    zenith = (await client.post(CREATE, json={"name": "Zenith Foods"}, headers=_h(first))).json()
    await _add_people(client, zenith, "Fleet")
    return first, first_department, zenith


async def _delete_zenith(client, first: dict, zenith: dict) -> None:
    body = {"organization_id": zenith["organization"]["id"], "confirm_name": "Zenith Foods", "password": DEFAULT_PASSWORD}
    resp = await client.post(DELETE, json=body, headers=_h(first))
    assert resp.status_code == 200, resp.text


async def _age(db_session, org_id: str, days: int) -> None:
    """Pretend the company was deleted ``days`` ago."""
    await set_org_context(db_session, org_id)
    # A real deletion stamps the company and every membership with the same time, so move both together.
    await db_session.execute(
        text("UPDATE memberships SET deactivated_at = now() - make_interval(days => :d) WHERE organization_id = :id"),
        {"d": days, "id": uuid.UUID(org_id)},
    )
    await db_session.execute(
        text("UPDATE organizations SET archived_at = now() - make_interval(days => :d) WHERE id = :id"),
        {"d": days, "id": uuid.UUID(org_id)},
    )


async def _count(db_session, table: str, org_id: str) -> int:
    await set_org_context(db_session, org_id)
    result = await db_session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": uuid.UUID(org_id)})
    return result.scalar_one()


# -- the ordering rule on its own ---------------------------------------------------------------


def test_children_are_removed_before_the_tables_they_point_to():
    order = order_for_deletion(["departments", "positions", "employees"], [("positions", "departments"), ("employees", "positions")])
    assert order == ["employees", "positions", "departments"]


def test_a_table_pointing_at_itself_is_fine():
    assert order_for_deletion(["employees"], [("employees", "employees")]) == ["employees"]


def test_an_unknown_loop_refuses_instead_of_guessing():
    with pytest.raises(RuntimeError, match="Unknown loop"):
        order_for_deletion(["a", "b"], [("a", "b"), ("b", "a")])


@pytest.mark.asyncio
async def test_the_real_tables_are_all_covered_in_a_working_order(db_session):
    order = await tables_to_purge(db_session)
    columns = await db_session.execute(
        text("SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'organization_id'")
    )
    assert set(order) == {row.table_name for row in columns}
    assert "organizations" not in order
    # A few of the real dependencies: employees before their roles before their departments; tasks before employees.
    assert order.index("employees") < order.index("positions") < order.index("departments")
    assert order.index("tasks") < order.index("employees")
    assert order.index("kpis") < order.index("departments")


# -- the purge itself ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_company_deleted_a_month_ago_is_erased_with_everything_in_it(client, db_session):
    first, first_department, zenith = await _two_companies_with_people(client, "pg_chidi1@example.com")
    zenith_id = zenith["organization"]["id"]
    await _delete_zenith(client, first, zenith)
    await _age(db_session, zenith_id, PURGE_AFTER_DAYS + 1)
    assert await _count(db_session, "employees", zenith_id) == 2

    removed = await purge_company(db_session, uuid.UUID(zenith_id))

    assert removed is not None
    assert removed["employees"] == 2 and removed["departments"] == 1 and removed["positions"] == 1
    assert removed["memberships"] >= 1 and removed["audit_log"] >= 1
    for table in ("employees", "departments", "positions", "memberships", "audit_log"):
        assert await _count(db_session, table, zenith_id) == 0
    gone = await db_session.execute(text("SELECT count(*) FROM organizations WHERE id = :id"), {"id": uuid.UUID(zenith_id)})
    assert gone.scalar_one() == 0
    # His other company and his own account are untouched.
    listing = await client.get(DEPARTMENTS, headers=_h(first))
    assert [d["id"] for d in listing.json()["data"]] == [first_department]
    assert (await client.get(f"{AUTH}/me", headers=_h(first))).status_code == 200


@pytest.mark.asyncio
async def test_a_company_deleted_recently_is_left_alone(client, db_session):
    first, _, zenith = await _two_companies_with_people(client, "pg_chidi2@example.com")
    zenith_id = zenith["organization"]["id"]
    await _delete_zenith(client, first, zenith)
    await _age(db_session, zenith_id, PURGE_AFTER_DAYS - 1)

    assert await purge_company(db_session, uuid.UUID(zenith_id)) is None

    assert await _count(db_session, "employees", zenith_id) == 2


@pytest.mark.asyncio
async def test_a_restored_or_live_company_is_never_erased(client, db_session):
    first, _, zenith = await _two_companies_with_people(client, "pg_chidi3@example.com")
    zenith_id = zenith["organization"]["id"]

    # A live company, however old.
    assert await purge_company(db_session, uuid.UUID(zenith_id)) is None
    # A deleted-then-restored one.
    await _delete_zenith(client, first, zenith)
    await _age(db_session, zenith_id, PURGE_AFTER_DAYS + 5)
    restored = await client.post(f"{AUTH}/restore-organization", json={"organization_id": zenith_id}, headers=_h(first))
    assert restored.status_code == 200
    assert await purge_company(db_session, uuid.UUID(zenith_id)) is None

    assert await _count(db_session, "employees", zenith_id) == 2


@pytest.mark.asyncio
async def test_a_company_that_is_already_gone_is_skipped(client, db_session):
    first, _, zenith = await _two_companies_with_people(client, "pg_chidi4@example.com")
    zenith_id = zenith["organization"]["id"]
    await _delete_zenith(client, first, zenith)
    await _age(db_session, zenith_id, PURGE_AFTER_DAYS + 1)
    assert await purge_company(db_session, uuid.UUID(zenith_id)) is not None

    assert await purge_company(db_session, uuid.UUID(zenith_id)) is None


@pytest.mark.asyncio
async def test_only_old_enough_deleted_companies_are_listed_as_due(client, db_session):
    first, _, zenith = await _two_companies_with_people(client, "pg_chidi5@example.com")
    zenith_id = zenith["organization"]["id"]
    await _delete_zenith(client, first, zenith)

    await _age(db_session, zenith_id, PURGE_AFTER_DAYS - 1)
    assert uuid.UUID(zenith_id) not in await list_due_for_purge(db_session)
    await _age(db_session, zenith_id, PURGE_AFTER_DAYS + 1)
    due = await list_due_for_purge(db_session)
    assert uuid.UUID(zenith_id) in due
    assert uuid.UUID(first["organization"]["id"]) not in due


@pytest.mark.asyncio
async def test_the_deleted_list_tells_the_owner_when_it_will_be_erased(client):
    first, _, zenith = await _two_companies_with_people(client, "pg_chidi6@example.com")
    await _delete_zenith(client, first, zenith)

    item = (await client.get(DELETED, headers=_h(first))).json()["data"][0]

    deleted_at = datetime.fromisoformat(item["deleted_at"])
    erased_on = datetime.fromisoformat(item["will_be_erased_on"])
    assert erased_on - deleted_at == timedelta(days=PURGE_AFTER_DAYS)
