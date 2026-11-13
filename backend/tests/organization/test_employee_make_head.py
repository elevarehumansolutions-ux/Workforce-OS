"""The Add Employee checkbox "Make this person head of <department>" (08_DECISIONS.md 2026-11-13).

Scenario: Adaeze adds Bayo as Head of Sales and ticks the box; Sales now shows Bayo as its head on
the Organization Structure page. Adding Bola later with the box ticked replaces him (the screen
asked first). Without the box nothing about the head changes.
"""
from datetime import date

import pytest

from tests.conftest import register_verified_and_login

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
AUDIT = "/api/v1/audit-log"


def _h(login) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _sales(client, email):
    login = await register_verified_and_login(client, email=email)
    headers = _h(login)
    dept = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)).json()["id"]
    role = (await client.post(POSITIONS, json={"department_id": dept, "title": "Head of Sales"}, headers=headers)).json()["id"]
    return headers, dept, role


async def _hire(client, headers, role, first, make_head=False):
    body = {
        "position_id": role, "first_name": first, "last_name": "Tester", "work_email": f"{first.lower()}@example.com",
        "start_date": date.today().isoformat(),
    }
    if make_head:
        body["make_department_head"] = True
    resp = await client.post(EMPLOYEES, json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _head_of(client, headers, dept):
    return (await client.get(f"{DEPARTMENTS}/{dept}", headers=headers)).json()["head_employee_id"]


@pytest.mark.asyncio
async def test_ticking_the_box_names_the_head_of_their_department(client):
    headers, dept, role = await _sales(client, "mh1@example.com")

    bayo = await _hire(client, headers, role, "Bayo", make_head=True)

    assert await _head_of(client, headers, dept) == bayo["id"]


@pytest.mark.asyncio
async def test_without_the_box_the_head_is_left_alone(client):
    headers, dept, role = await _sales(client, "mh2@example.com")

    await _hire(client, headers, role, "Bayo")

    assert await _head_of(client, headers, dept) is None


@pytest.mark.asyncio
async def test_ticking_the_box_replaces_the_current_head_and_the_change_is_logged(client):
    headers, dept, role = await _sales(client, "mh3@example.com")
    bayo = await _hire(client, headers, role, "Bayo", make_head=True)

    bola = await _hire(client, headers, role, "Bola", make_head=True)

    assert await _head_of(client, headers, dept) == bola["id"]
    rows = (await client.get(AUDIT, params={"entity_type": "department"}, headers=headers)).json()["data"]
    changes = [r["changes"] for r in rows if r["action"] == "update"]
    assert any(
        c["old"].get("head_employee_id") == bayo["id"] and c["new"].get("head_employee_id") == bola["id"] for c in changes
    )
