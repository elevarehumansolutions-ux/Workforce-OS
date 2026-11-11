"""Reporting managers filled in from the position chart (08_DECISIONS.md 2026-11-11).

Scenario: Adaeze's Sales department has a CEO, a Head of Sales who reports to the CEO, and a Sales
Rep who reports to the Head. People are added in any order. When exactly one person holds the role
above, the manager is filled in for her; when it is unclear, or she chose one herself, nothing changes.
"""
from datetime import date

import pytest

from tests.conftest import register_verified_and_login

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"


def _h(login) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _sales(client, email):
    """Login plus the three roles: CEO <- Head of Sales <- Sales Rep. Returns (headers, {title: id})."""
    login = await register_verified_and_login(client, email=email)
    headers = _h(login)
    dept = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)).json()["id"]
    ids = {}
    for title, boss in (("CEO", None), ("Head of Sales", "CEO"), ("Sales Rep", "Head of Sales")):
        body = {"department_id": dept, "title": title}
        if boss:
            body["reports_to_position_id"] = ids[boss]
        ids[title] = (await client.post(POSITIONS, json=body, headers=headers)).json()["id"]
    return headers, ids


async def _hire(client, headers, role_id, first, manager_id=None):
    body = {
        "position_id": role_id,
        "first_name": first,
        "last_name": "Tester",
        "work_email": f"{first.lower()}@example.com",
        "start_date": date.today().isoformat(),
    }
    if manager_id:
        body["manager_id"] = manager_id
    resp = await client.post(EMPLOYEES, json=body, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _manager_of(client, headers, employee_id):
    return (await client.get(f"{EMPLOYEES}/{employee_id}", headers=headers)).json()["manager_id"]


@pytest.mark.asyncio
async def test_a_new_hire_gets_the_only_holder_of_the_role_above_as_manager(client):
    """Ada is the one CEO; Bayo joins as Head of Sales with no manager chosen: Ada becomes it."""
    headers, roles = await _sales(client, "am1@example.com")
    ada = await _hire(client, headers, roles["CEO"], "Ada")

    bayo = await _hire(client, headers, roles["Head of Sales"], "Bayo")

    assert bayo["manager_id"] == ada["id"]


@pytest.mark.asyncio
async def test_a_boss_added_last_gets_their_team_linked(client):
    """Chidi (Sales Rep) was added first with nobody above; when Bayo is added, Chidi reports to him."""
    headers, roles = await _sales(client, "am2@example.com")
    chidi = await _hire(client, headers, roles["Sales Rep"], "Chidi")
    assert await _manager_of(client, headers, chidi["id"]) is None

    bayo = await _hire(client, headers, roles["Head of Sales"], "Bayo")

    assert await _manager_of(client, headers, chidi["id"]) == bayo["id"]


@pytest.mark.asyncio
async def test_a_manager_chosen_by_hand_is_never_overwritten(client):
    """Chidi was given Ada on purpose; adding Bayo (Head of Sales) does not take him away."""
    headers, roles = await _sales(client, "am3@example.com")
    ada = await _hire(client, headers, roles["CEO"], "Ada")
    chidi = await _hire(client, headers, roles["Sales Rep"], "Chidi", manager_id=ada["id"])

    await _hire(client, headers, roles["Head of Sales"], "Bayo")

    assert await _manager_of(client, headers, chidi["id"]) == ada["id"]


@pytest.mark.asyncio
async def test_two_holders_of_the_role_above_means_nothing_is_guessed(client):
    """Bayo and Bola are both Head of Sales: Chidi's manager is a human choice, so it stays empty."""
    headers, roles = await _sales(client, "am4@example.com")
    await _hire(client, headers, roles["Head of Sales"], "Bayo")
    await _hire(client, headers, roles["Head of Sales"], "Bola")

    chidi = await _hire(client, headers, roles["Sales Rep"], "Chidi")

    assert chidi["manager_id"] is None


@pytest.mark.asyncio
async def test_a_second_holder_does_not_take_over_the_team(client):
    """Bayo already leads Chidi; adding Bola as a second Head of Sales changes nothing."""
    headers, roles = await _sales(client, "am5@example.com")
    chidi = await _hire(client, headers, roles["Sales Rep"], "Chidi")
    bayo = await _hire(client, headers, roles["Head of Sales"], "Bayo")

    await _hire(client, headers, roles["Head of Sales"], "Bola")

    assert await _manager_of(client, headers, chidi["id"]) == bayo["id"]


@pytest.mark.asyncio
async def test_someone_who_left_is_not_picked_as_manager(client):
    """Bayo is offboarded; a new Sales Rep is not linked to him."""
    headers, roles = await _sales(client, "am6@example.com")
    bayo = await _hire(client, headers, roles["Head of Sales"], "Bayo")
    await client.post(f"{EMPLOYEES}/{bayo['id']}/offboard", headers=headers)

    chidi = await _hire(client, headers, roles["Sales Rep"], "Chidi")

    assert chidi["manager_id"] is None


@pytest.mark.asyncio
async def test_moving_someone_into_a_role_links_them_too(client):
    """Chidi starts as CEO; moved to Sales Rep, the one Head of Sales (Bayo) becomes his manager."""
    headers, roles = await _sales(client, "am7@example.com")
    bayo = await _hire(client, headers, roles["Head of Sales"], "Bayo")
    chidi = await _hire(client, headers, roles["CEO"], "Chidi")

    resp = await client.patch(f"{EMPLOYEES}/{chidi['id']}", json={"position_id": roles["Sales Rep"]}, headers=headers)

    assert resp.status_code == 200
    assert await _manager_of(client, headers, chidi["id"]) == bayo["id"]
