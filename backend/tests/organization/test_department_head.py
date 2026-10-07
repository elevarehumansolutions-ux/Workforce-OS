"""HTTP-level tests for a department's head (``departments.head_employee_id``).

One named person per department, set by HR; any active employee of the same
organization qualifies; offboarding the head clears the field and tells the
HR administrators; reinstating does not restore it (08_DECISIONS.md
2026-10-06).
"""
import uuid
from unittest.mock import MagicMock

import pytest

from tests.conftest import register_verified_and_login

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"
NOTIFICATIONS = "/api/v1/notifications"
AUDIT = "/api/v1/audit-log"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org(client, email: str) -> tuple[dict, dict, str, str, str]:
    """An org owner with two departments (Dispatch, Fleet) and a position in Dispatch."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    dispatch = (await client.post(DEPARTMENTS, json={"name": "Dispatch"}, headers=h)).json()["id"]
    fleet = (await client.post(DEPARTMENTS, json={"name": "Fleet"}, headers=h)).json()["id"]
    pos = await client.post(POSITIONS, json={"department_id": dispatch, "title": "Officer"}, headers=h)
    return owner, h, dispatch, fleet, pos.json()["id"]


async def _employee(client, h, position_id: str, name: str) -> str:
    resp = await client.post(
        EMPLOYEES,
        json={
            "position_id": position_id,
            "first_name": name,
            "last_name": "Test",
            "work_email": f"{name.lower()}.{uuid.uuid4().hex[:6]}@example.com",
            "start_date": "2026-01-01",
        },
        headers=h,
    )
    return resp.json()["id"]


async def _set_head(client, h, department_id: str, employee_id: str | None):
    return await client.patch(f"{DEPARTMENTS}/{department_id}", json={"head_employee_id": employee_id}, headers=h)


async def _titles(client, h) -> list[str]:
    return [n["title"] for n in (await client.get(NOTIFICATIONS, headers=h)).json()]


@pytest.mark.asyncio
async def test_hr_can_name_a_head_and_it_shows_on_the_department(client):
    """The head is stored, returned by PATCH, and returned by GET."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner1@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")

    patched = await _set_head(client, h, dispatch, tunde)
    fetched = await client.get(f"{DEPARTMENTS}/{dispatch}", headers=h)
    listed = await client.get(DEPARTMENTS, headers=h)

    assert patched.status_code == 200
    assert patched.json()["head_employee_id"] == tunde
    assert fetched.json()["head_employee_id"] == tunde
    assert {d["id"]: d["head_employee_id"] for d in listed.json()["data"]}[dispatch] == tunde


@pytest.mark.asyncio
async def test_a_new_department_has_no_head_and_other_edits_leave_it_alone(client):
    """Null by default; editing the name neither sets nor clears the head."""
    owner, h, dispatch, fleet, position_id = await _org(client, "dh_owner2@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    assert (await client.get(f"{DEPARTMENTS}/{dispatch}", headers=h)).json()["head_employee_id"] is None
    await _set_head(client, h, dispatch, tunde)

    renamed = await client.patch(f"{DEPARTMENTS}/{dispatch}", json={"name": "Dispatch & Delivery"}, headers=h)

    assert renamed.json()["head_employee_id"] == tunde


@pytest.mark.asyncio
async def test_null_clears_the_head(client):
    """Sending an explicit null removes the head."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner3@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    await _set_head(client, h, dispatch, tunde)

    cleared = await _set_head(client, h, dispatch, None)

    assert cleared.status_code == 200
    assert cleared.json()["head_employee_id"] is None


@pytest.mark.asyncio
async def test_the_head_does_not_have_to_belong_to_that_department(client):
    """Tunde's position is in Dispatch, yet he can head Fleet; and one person can head two departments."""
    owner, h, dispatch, fleet, position_id = await _org(client, "dh_owner4@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")

    first = await _set_head(client, h, dispatch, tunde)
    second = await _set_head(client, h, fleet, tunde)

    assert first.status_code == second.status_code == 200
    assert second.json()["head_employee_id"] == tunde


@pytest.mark.asyncio
async def test_an_unknown_or_other_organizations_employee_cannot_be_head(client):
    """404 for an id that doesn't exist and for one that belongs to another org."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner5@example.com")
    other_owner, other_h, _, _, other_position = await _org(client, "dh_other5@example.com")
    foreign = await _employee(client, other_h, other_position, "Foreigner")

    unknown = await _set_head(client, h, dispatch, str(uuid.uuid4()))
    cross_org = await _set_head(client, h, dispatch, foreign)

    assert unknown.status_code == 404
    assert cross_org.status_code == 404
    assert (await client.get(f"{DEPARTMENTS}/{dispatch}", headers=h)).json()["head_employee_id"] is None


@pytest.mark.asyncio
async def test_an_offboarded_employee_cannot_be_named_head(client):
    """Only active employees can head a department."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner6@example.com")
    gone = await _employee(client, h, position_id, "Gone")
    await client.post(f"{EMPLOYEES}/{gone}/offboard", headers=h)

    resp = await _set_head(client, h, dispatch, gone)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_only_hr_admins_can_set_a_head(client, monkeypatch):
    """A manager gets 403."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner7@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    await client.post(MEMBERSHIPS, json={"email": "dh_mgr7@example.com", "role": "manager"}, headers=h)
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    manager = (await client.post(
        f"{AUTH}/accept-invite",
        json={"token": token, "full_name": "Test Manager", "password": "Password123#",
              "confirm_password": "Password123#"},
    )).json()

    resp = await _set_head(client, _auth_header(manager["access_token"]), dispatch, tunde)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_changing_the_head_is_audit_logged_with_old_and_new(client):
    """The audit trail records who the head was and who it became."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner8@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    bola = await _employee(client, h, position_id, "Bola")
    await _set_head(client, h, dispatch, tunde)
    await _set_head(client, h, dispatch, bola)

    audit = await client.get(AUDIT, params={"entity_type": "department", "entity_id": dispatch}, headers=h)

    changes = [e["changes"] for e in audit.json()["data"] if e["action"] == "update"]
    assert any(
        c["old"].get("head_employee_id") == tunde and c["new"].get("head_employee_id") == bola for c in changes
    )


@pytest.mark.asyncio
async def test_offboarding_the_head_clears_it_audits_it_and_notifies_hr(client):
    """Tunde leaves: Dispatch has no head, there is an audit entry, and HR is told."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner9@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    await _set_head(client, h, dispatch, tunde)

    off = await client.post(f"{EMPLOYEES}/{tunde}/offboard", headers=h)

    assert off.status_code == 200
    assert (await client.get(f"{DEPARTMENTS}/{dispatch}", headers=h)).json()["head_employee_id"] is None
    audit = await client.get(AUDIT, params={"entity_type": "department", "entity_id": dispatch}, headers=h)
    cleared = [e for e in audit.json()["data"] if e["changes"].get("reason") == "the department head was offboarded"]
    assert len(cleared) == 1
    assert cleared[0]["changes"]["old"]["head_employee_id"] == tunde
    assert cleared[0]["changes"]["new"]["head_employee_id"] is None
    emp_audit = await client.get(AUDIT, params={"entity_type": "employee", "entity_id": tunde}, headers=h)
    offboard_entry = [e for e in emp_audit.json()["data"] if e["action"] == "offboard"][0]
    assert offboard_entry["changes"]["departments_head_cleared"] == [dispatch]
    assert "A department needs a new head" in await _titles(client, h)


@pytest.mark.asyncio
async def test_offboarding_someone_who_heads_two_departments_clears_both_with_one_notice(client):
    """One notification names both departments."""
    owner, h, dispatch, fleet, position_id = await _org(client, "dh_owner10@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    await _set_head(client, h, dispatch, tunde)
    await _set_head(client, h, fleet, tunde)

    await client.post(f"{EMPLOYEES}/{tunde}/offboard", headers=h)

    for dept in (dispatch, fleet):
        assert (await client.get(f"{DEPARTMENTS}/{dept}", headers=h)).json()["head_employee_id"] is None
    notes = [n for n in (await client.get(NOTIFICATIONS, headers=h)).json() if n["title"] == "A department needs a new head"]
    assert len(notes) == 1
    assert "Dispatch" in notes[0]["body"] and "Fleet" in notes[0]["body"]


@pytest.mark.asyncio
async def test_offboarding_someone_who_is_not_a_head_changes_no_department_and_sends_no_notice(client):
    """Bola leaves; Tunde is still Dispatch's head and nobody is told anything."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner11@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    bola = await _employee(client, h, position_id, "Bola")
    await _set_head(client, h, dispatch, tunde)

    await client.post(f"{EMPLOYEES}/{bola}/offboard", headers=h)

    assert (await client.get(f"{DEPARTMENTS}/{dispatch}", headers=h)).json()["head_employee_id"] == tunde
    assert "A department needs a new head" not in await _titles(client, h)


@pytest.mark.asyncio
async def test_reinstating_does_not_restore_the_head(client):
    """HR chooses again; the old headship is not silently brought back."""
    owner, h, dispatch, _, position_id = await _org(client, "dh_owner12@example.com")
    tunde = await _employee(client, h, position_id, "Tunde")
    await _set_head(client, h, dispatch, tunde)
    await client.post(f"{EMPLOYEES}/{tunde}/offboard", headers=h)

    back = await client.post(f"{EMPLOYEES}/{tunde}/reinstate", headers=h)

    assert back.status_code == 200
    assert (await client.get(f"{DEPARTMENTS}/{dispatch}", headers=h)).json()["head_employee_id"] is None
    again = await _set_head(client, h, dispatch, tunde)
    assert again.status_code == 200 and again.json()["head_employee_id"] == tunde
