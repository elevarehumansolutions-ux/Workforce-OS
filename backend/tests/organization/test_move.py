"""Moving a person to another role, and a role to another department (08_DECISIONS.md 2026-11-25).

Scenario: Bayo heads Sales. HR moves him to a role in Marketing: Sales is left without a head, and
his manager becomes whoever alone holds the role above his new one.
"""
import uuid

import pytest

from tests.organization.test_employee_make_head import (
    DEPARTMENTS, EMPLOYEES, POSITIONS, _h, _head_of, _hire, _sales,
)
from tests.conftest import register_verified_and_login


async def _marketing(client, headers):
    """A second department with a lead role and a writer role reporting to it."""
    dept = (await client.post(DEPARTMENTS, json={"name": "Marketing"}, headers=headers)).json()["id"]
    lead = (await client.post(POSITIONS, json={"department_id": dept, "title": "Marketing Lead"}, headers=headers)).json()["id"]
    writer = (await client.post(
        POSITIONS, json={"department_id": dept, "title": "Writer", "reports_to_position_id": lead}, headers=headers
    )).json()["id"]
    return dept, lead, writer


async def _move_person(client, headers, person_id, role_id):
    return await client.post(f"{EMPLOYEES}/{person_id}/move", json={"position_id": role_id}, headers=headers)


@pytest.mark.asyncio
async def test_moving_a_head_leaves_the_old_department_without_one_and_gives_the_new_manager(client):
    headers, sales, sales_role = await _sales(client, "mv1@example.com")
    marketing, lead, writer = await _marketing(client, headers)
    ada = await _hire(client, headers, lead, "Ada")
    bayo = await _hire(client, headers, sales_role, "Bayo", make_head=True)

    resp = await _move_person(client, headers, bayo["id"], writer)

    assert resp.status_code == 200, resp.text
    assert resp.json()["position_id"] == writer
    assert resp.json()["manager_id"] == ada["id"]
    assert await _head_of(client, headers, sales) is None
    assert await _head_of(client, headers, marketing) is None  # moving never makes someone a head


@pytest.mark.asyncio
async def test_moving_a_role_takes_its_people_and_ends_their_headship_of_the_old_department(client):
    headers, sales, sales_role = await _sales(client, "mv2@example.com")
    marketing, _, _ = await _marketing(client, headers)
    bayo = await _hire(client, headers, sales_role, "Bayo", make_head=True)

    resp = await client.post(f"{POSITIONS}/{sales_role}/move", json={"department_id": marketing}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["department_id"] == marketing
    person = (await client.get(f"{EMPLOYEES}/{bayo['id']}", headers=headers)).json()
    assert person["position_id"] == sales_role  # they stay in the role, which is now elsewhere
    assert await _head_of(client, headers, sales) is None


@pytest.mark.asyncio
async def test_a_move_that_changes_nothing_or_names_something_unknown_is_refused(client):
    headers, sales, sales_role = await _sales(client, "mv3@example.com")
    bayo = await _hire(client, headers, sales_role, "Bayo")
    unknown = str(uuid.uuid4())

    same_role = await _move_person(client, headers, bayo["id"], sales_role)
    unknown_role = await _move_person(client, headers, bayo["id"], unknown)
    same_department = await client.post(
        f"{POSITIONS}/{sales_role}/move", json={"department_id": sales}, headers=headers
    )
    unknown_department = await client.post(
        f"{POSITIONS}/{sales_role}/move", json={"department_id": unknown}, headers=headers
    )

    assert same_role.status_code == 422
    assert unknown_role.status_code == 404
    assert same_department.status_code == 422
    assert unknown_department.status_code == 404


@pytest.mark.asyncio
async def test_another_companys_role_and_department_cannot_be_used(client):
    """The ownership check on all four paths: move, edit, create a role and create a person."""
    headers, _, sales_role = await _sales(client, "mv4@example.com")
    bayo = await _hire(client, headers, sales_role, "Bayo")
    their_headers, their_department, their_role = await _sales(client, "mv4other@example.com")

    attempts = [
        await _move_person(client, headers, bayo["id"], their_role),
        await client.patch(f"{EMPLOYEES}/{bayo['id']}", json={"position_id": their_role}, headers=headers),
        await client.patch(f"{POSITIONS}/{sales_role}", json={"department_id": their_department}, headers=headers),
        await client.post(
            POSITIONS, json={"department_id": their_department, "title": "Sneaky"}, headers=headers
        ),
        await client.post(
            EMPLOYEES,
            json={"position_id": their_role, "first_name": "S", "last_name": "N",
                  "work_email": "sneaky@example.com", "start_date": "2026-01-01"},
            headers=headers,
        ),
    ]

    assert [resp.status_code for resp in attempts] == [404] * len(attempts)


@pytest.mark.asyncio
async def test_only_hr_may_move(client):
    headers, sales, sales_role = await _sales(client, "mv5@example.com")
    stranger = await register_verified_and_login(client, email="mv5stranger@example.com")
    stranger_headers = _h(stranger)
    unauthenticated = await client.post(f"{EMPLOYEES}/{uuid.uuid4()}/move", json={"position_id": sales_role})
    # HR of another company cannot move this company's role.
    other_company = await client.post(
        f"{POSITIONS}/{sales_role}/move", json={"department_id": sales}, headers=stranger_headers
    )

    assert unauthenticated.status_code == 401
    assert other_company.status_code == 404
