"""HTTP-level tests for /attendance: clock-in, clock-out, and history.

Covers the happy path end to end, the "no employee record" and "not clocked
in" errors, who may read whose history, and that date filters are calendar
days on the organization's wall clock, not in UTC.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.modules.attendance.models import AttendanceRecord
from tests.conftest import register_verified_and_login, set_org_context

ATTENDANCE = "/api/v1/attendance"
DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org(client, email: str) -> tuple[dict, dict, str]:
    """Register an org owner; returns (owner, auth header, position_id)."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "Officer"}, headers=h
    )
    return owner, h, pos.json()["id"]


async def _employee_for(client, h, position_id: str, user_id: str | None, email: str) -> str:
    body = {
        "position_id": position_id,
        "first_name": "Test",
        "last_name": "Person",
        "work_email": email,
        "start_date": "2026-01-01",
    }
    if user_id:
        body["user_id"] = user_id
    return (await client.post(EMPLOYEES, json=body, headers=h)).json()["id"]


async def _teammate(client, monkeypatch, h, email: str, role: str) -> dict:
    """Invite and accept a teammate; returns the accept-invite body."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(MEMBERSHIPS, json={"email": email, "role": role}, headers=h)
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    resp = await client.post(
        f"{AUTH}/accept-invite",
        json={"token": token, "full_name": "Test Teammate", "password": "Password123#",
              "confirm_password": "Password123#"},
    )
    return resp.json()


@pytest.mark.asyncio
async def test_clock_in_and_out_end_to_end(client):
    """The widget's whole day: clock in, tap again, clock out, tap again, clock in the next day."""
    owner, h, position_id = await _org(client, "att_rt1@example.com")
    await _employee_for(client, h, position_id, owner["user"]["id"], "att_rt1@example.com")

    first = await client.post(f"{ATTENDANCE}/clock-in", headers=h)
    again = await client.post(f"{ATTENDANCE}/clock-in", headers=h)
    out = await client.post(f"{ATTENDANCE}/clock-out", headers=h)
    out_again = await client.post(f"{ATTENDANCE}/clock-out", headers=h)
    next_day = await client.post(f"{ATTENDANCE}/clock-in", headers=h)

    assert first.status_code == 200
    assert first.json()["already_clocked_in"] is False
    assert first.json()["record"]["clock_out_at"] is None
    assert again.json()["already_clocked_in"] is True
    assert again.json()["record"]["id"] == first.json()["record"]["id"]
    assert out.status_code == 200
    assert out.json()["id"] == first.json()["record"]["id"]
    assert out.json()["closed_by"] == "employee"
    assert out.json()["clock_out_at"] is not None
    assert out_again.status_code == 409
    assert out_again.json()["code"] == "NOT_CLOCKED_IN"
    assert next_day.json()["already_clocked_in"] is False
    assert next_day.json()["record"]["id"] != first.json()["record"]["id"]

    history = await client.get(ATTENDANCE, headers=h)
    records = history.json()["data"]
    assert [r["id"] for r in records] == [next_day.json()["record"]["id"], first.json()["record"]["id"]]
    assert records[0]["clock_out_at"] is None


@pytest.mark.asyncio
async def test_a_member_with_no_employee_record_gets_a_clear_409_everywhere(client):
    """The founder has a login but no employee record until HR adds them."""
    owner, h, _ = await _org(client, "att_rt2@example.com")

    for method, path in [("post", "/clock-in"), ("post", "/clock-out"), ("get", "")]:
        resp = await getattr(client, method)(f"{ATTENDANCE}{path}", headers=h)
        assert resp.status_code == 409, path
        assert resp.json()["code"] == "NO_EMPLOYEE_PROFILE", path


@pytest.mark.asyncio
async def test_attendance_requires_authentication(client):
    """No token, no attendance."""
    for method, path in [("post", "/clock-in"), ("post", "/clock-out"), ("get", "")]:
        resp = await getattr(client, method)(f"{ATTENDANCE}{path}")
        assert resp.status_code == 401, path


@pytest.mark.asyncio
async def test_date_filters_are_calendar_days_in_the_organizations_timezone(client, db_session):
    """A 00:30 Lagos clock-in is 23:30 the day before in UTC, and still belongs to the Lagos day."""
    owner, h, position_id = await _org(client, "att_rt3@example.com")
    employee_id = await _employee_for(client, h, position_id, owner["user"]["id"], "att_rt3@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    for clock_in in [
        datetime(2026, 10, 1, 23, 30, tzinfo=UTC),   # 2 Oct 00:30 in Lagos (UTC+1)
        datetime(2026, 10, 2, 10, 0, tzinfo=UTC),    # 2 Oct 11:00 in Lagos
        datetime(2026, 10, 3, 10, 0, tzinfo=UTC),    # 3 Oct in Lagos
    ]:
        db_session.add(AttendanceRecord(
            organization_id=org_id, employee_id=employee_id, clock_in_at=clock_in,
            clock_out_at=clock_in + timedelta(hours=1), closed_by="employee",
        ))
    await db_session.flush()

    second = await client.get(ATTENDANCE, params={"date_from": "2026-10-02", "date_to": "2026-10-02"}, headers=h)
    before = await client.get(ATTENDANCE, params={"date_to": "2026-10-01"}, headers=h)
    from_third = await client.get(ATTENDANCE, params={"date_from": "2026-10-03"}, headers=h)

    assert second.json()["pagination"]["total"] == 2        # both Lagos-October-2nd records
    assert before.json()["pagination"]["total"] == 0        # the 23:30 UTC record is NOT on the 1st
    assert from_third.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_a_backwards_date_range_is_rejected(client):
    """date_from after date_to can never match anything."""
    owner, h, position_id = await _org(client, "att_rt4@example.com")
    await _employee_for(client, h, position_id, owner["user"]["id"], "att_rt4@example.com")

    resp = await client.get(ATTENDANCE, params={"date_from": "2026-10-05", "date_to": "2026-10-01"}, headers=h)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_history_is_paginated_newest_first(client, db_session):
    """Three records, two per page: the envelope tells the client there is more."""
    owner, h, position_id = await _org(client, "att_rt5@example.com")
    employee_id = await _employee_for(client, h, position_id, owner["user"]["id"], "att_rt5@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    base = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    for day in range(3):
        clock_in = base + timedelta(days=day)
        db_session.add(AttendanceRecord(
            organization_id=org_id, employee_id=employee_id, clock_in_at=clock_in,
            clock_out_at=clock_in + timedelta(hours=8), closed_by="employee",
        ))
    await db_session.flush()

    page1 = await client.get(ATTENDANCE, params={"limit": 2}, headers=h)
    page2 = await client.get(ATTENDANCE, params={"limit": 2, "page": 2}, headers=h)

    assert [r["clock_in_at"][:10] for r in page1.json()["data"]] == ["2026-09-03", "2026-09-02"]
    assert page1.json()["pagination"]["total"] == 3
    assert page1.json()["pagination"]["has_next"] is True
    assert [r["clock_in_at"][:10] for r in page2.json()["data"]] == ["2026-09-01"]


@pytest.mark.asyncio
async def test_who_may_read_whose_history(client, monkeypatch):
    """Employees and managers see only themselves; HR admins and business executives see anyone."""
    owner, h, position_id = await _org(client, "att_rt6@example.com")
    worker = await _teammate(client, monkeypatch, h, "att_worker6@example.com", "employee")
    worker_employee = await _employee_for(client, h, position_id, worker["user"]["id"], "att_worker6@example.com")
    manager = await _teammate(client, monkeypatch, h, "att_mgr6@example.com", "manager")
    executive = await _teammate(client, monkeypatch, h, "att_exec6@example.com", "business_executive")
    worker_h = _auth_header(worker["access_token"])
    await client.post(f"{ATTENDANCE}/clock-in", headers=worker_h)

    as_worker_self = await client.get(ATTENDANCE, params={"employee_id": worker_employee}, headers=worker_h)
    as_manager = await client.get(
        ATTENDANCE, params={"employee_id": worker_employee}, headers=_auth_header(manager["access_token"])
    )
    as_hr = await client.get(ATTENDANCE, params={"employee_id": worker_employee}, headers=h)
    as_exec = await client.get(
        ATTENDANCE, params={"employee_id": worker_employee}, headers=_auth_header(executive["access_token"])
    )

    assert as_worker_self.status_code == 200
    assert as_manager.status_code == 403
    assert as_hr.status_code == 200 and as_hr.json()["pagination"]["total"] == 1
    assert as_exec.status_code == 200 and as_exec.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_an_unknown_or_other_organizations_employee_is_a_404_for_privileged_viewers(client):
    """HR admins can read anyone in their own org, and nobody outside it."""
    owner, h, _ = await _org(client, "att_rt7@example.com")
    other_owner, other_h, other_position = await _org(client, "att_rt7b@example.com")
    foreign_employee = await _employee_for(
        client, other_h, other_position, other_owner["user"]["id"], "att_rt7b@example.com"
    )

    unknown = await client.get(ATTENDANCE, params={"employee_id": str(uuid.uuid4())}, headers=h)
    foreign = await client.get(ATTENDANCE, params={"employee_id": foreign_employee}, headers=h)

    assert unknown.status_code == 404
    assert foreign.status_code == 404
