"""Service-level tests for AttendanceService.clock_in.

Drives the service against the real database, with the employee created
through the real API so the user-to-employee link is genuine.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core.exceptions import (
    NoEmployeeProfileException,
    NotClockedInException,
    ValidationException,
)
from app.modules.attendance.models import AttendanceRecord
from app.modules.attendance.repository import AttendanceRepository
from app.modules.attendance.service import AttendanceService
from tests.conftest import register_verified_and_login, set_org_context

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
AUDIT = "/api/v1/audit-log"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _owner_who_is_also_an_employee(client, email: str) -> tuple[dict, str]:
    """Register an owner and give them an employee record linked to their login."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "Officer"}, headers=h
    )
    emp = await client.post(
        EMPLOYEES,
        json={
            "position_id": pos.json()["id"],
            "user_id": owner["user"]["id"],
            "first_name": "Chidi",
            "last_name": "Obi",
            "work_email": email,
            "start_date": "2026-01-01",
        },
        headers=h,
    )
    return owner, emp.json()["id"]


async def _open_count(db_session, employee_id: str) -> int:
    result = await db_session.execute(
        select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee_id, AttendanceRecord.clock_out_at.is_(None)
        )
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_first_clock_in_creates_an_open_record_and_is_audit_logged(client, db_session):
    """Clocking in opens a record for the caller's employee and says it wasn't already open."""
    owner, employee_id = await _owner_who_is_also_an_employee(client, "att_svc1@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    record, already = await AttendanceService(db_session).clock_in(owner["user"]["id"], org_id)

    assert already is False
    assert str(record.employee_id) == employee_id
    assert record.clock_out_at is None
    assert record.clock_in_at <= datetime.now(UTC)
    audit = await client.get(
        AUDIT, params={"entity_type": "attendance_record"}, headers=_auth_header(owner["access_token"])
    )
    entries = [e for e in audit.json()["data"] if e["action"] == "clock_in"]
    assert len(entries) == 1
    assert entries[0]["entity_id"] == str(record.id)


@pytest.mark.asyncio
async def test_clocking_in_again_returns_the_same_record_and_logs_nothing_new(client, db_session):
    """A repeat clock-in is a harmless retry: same record, flagged as already clocked in."""
    owner, employee_id = await _owner_who_is_also_an_employee(client, "att_svc2@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    service = AttendanceService(db_session)

    first, first_flag = await service.clock_in(owner["user"]["id"], org_id)
    second, second_flag = await service.clock_in(owner["user"]["id"], org_id)

    assert (first_flag, second_flag) == (False, True)
    assert first.id == second.id
    assert await _open_count(db_session, employee_id) == 1
    audit = await client.get(
        AUDIT, params={"entity_type": "attendance_record"}, headers=_auth_header(owner["access_token"])
    )
    assert len([e for e in audit.json()["data"] if e["action"] == "clock_in"]) == 1


@pytest.mark.asyncio
async def test_losing_a_simultaneous_clock_in_race_returns_the_winners_record(client, db_session):
    """If another request already took the open slot, clock_in returns that record, adding nothing.

    Written straight into the table, standing in for a concurrent request that
    won the race. The service has no "look first" step to be fooled by: its
    insert collides on the one-open-record index and reads the winner back.
    """
    owner, employee_id = await _owner_who_is_also_an_employee(client, "att_svc3@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    winner = await AttendanceRepository(db_session).create_open_record(
        org_id, employee_id, datetime.now(UTC)
    )

    record, already = await AttendanceService(db_session).clock_in(owner["user"]["id"], org_id)

    assert already is True
    assert record.id == winner.id
    assert await _open_count(db_session, employee_id) == 1
    audit = await client.get(
        AUDIT, params={"entity_type": "attendance_record"}, headers=_auth_header(owner["access_token"])
    )
    assert [e for e in audit.json()["data"] if e["action"] == "clock_in"] == []


@pytest.mark.asyncio
async def test_a_user_with_no_employee_record_cannot_clock_in(client, db_session):
    """The founder has a login but no employee record until HR creates one."""
    owner = await register_verified_and_login(client, email="att_svc4@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    with pytest.raises(NoEmployeeProfileException) as exc:
        await AttendanceService(db_session).clock_in(owner["user"]["id"], org_id)

    assert exc.value.code == "NO_EMPLOYEE_PROFILE"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_an_offboarded_employee_cannot_clock_in(client, db_session):
    """Offboarding ends attendance as well as login."""
    owner, employee_id = await _owner_who_is_also_an_employee(client, "att_svc5@example.com")
    org_id = owner["organization"]["id"]
    await client.post(f"{EMPLOYEES}/{employee_id}/offboard", headers=_auth_header(owner["access_token"]))
    await set_org_context(db_session, org_id)

    with pytest.raises(ValidationException):
        await AttendanceService(db_session).clock_in(owner["user"]["id"], org_id)


@pytest.mark.asyncio
async def test_clock_out_closes_the_open_record_as_the_employee_and_is_audit_logged(client, db_session):
    """Clocking out ends the record, credits the employee, and frees the next clock-in."""
    owner, employee_id = await _owner_who_is_also_an_employee(client, "att_svc6@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    service = AttendanceService(db_session)
    opened, _ = await service.clock_in(owner["user"]["id"], org_id)

    closed = await service.clock_out(owner["user"]["id"], org_id)

    assert closed.id == opened.id
    assert closed.clock_out_at is not None and closed.clock_out_at >= closed.clock_in_at
    assert closed.closed_by == "employee"
    assert closed.close_reason is None
    assert await _open_count(db_session, employee_id) == 0
    audit = await client.get(
        AUDIT, params={"entity_type": "attendance_record"}, headers=_auth_header(owner["access_token"])
    )
    assert len([e for e in audit.json()["data"] if e["action"] == "clock_out"]) == 1
    again, already = await service.clock_in(owner["user"]["id"], org_id)
    assert already is False and again.id != opened.id


@pytest.mark.asyncio
async def test_clocking_out_when_not_clocked_in_is_a_conflict(client, db_session):
    """There is nothing to close: a clear 409, not a silent success."""
    owner, _ = await _owner_who_is_also_an_employee(client, "att_svc7@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    with pytest.raises(NotClockedInException) as exc:
        await AttendanceService(db_session).clock_out(owner["user"]["id"], org_id)

    assert exc.value.code == "NOT_CLOCKED_IN"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_second_clock_out_is_refused_and_the_first_time_stands(client, db_session):
    """A double-tap on Clock Out can't overwrite the first clock-out time or log it twice."""
    owner, _ = await _owner_who_is_also_an_employee(client, "att_svc8@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    service = AttendanceService(db_session)
    await service.clock_in(owner["user"]["id"], org_id)
    first = await service.clock_out(owner["user"]["id"], org_id)
    first_out = first.clock_out_at

    with pytest.raises(NotClockedInException):
        await service.clock_out(owner["user"]["id"], org_id)

    row = (await db_session.execute(select(AttendanceRecord).where(AttendanceRecord.id == first.id))).scalar_one()
    assert row.clock_out_at == first_out
    audit = await client.get(
        AUDIT, params={"entity_type": "attendance_record"}, headers=_auth_header(owner["access_token"])
    )
    assert len([e for e in audit.json()["data"] if e["action"] == "clock_out"]) == 1


@pytest.mark.asyncio
async def test_a_user_with_no_employee_record_cannot_clock_out_either(client, db_session):
    """Same rule as clocking in: attendance belongs to the employee record."""
    owner = await register_verified_and_login(client, email="att_svc9@example.com")
    org_id = owner["organization"]["id"]
    await set_org_context(db_session, org_id)

    with pytest.raises(NoEmployeeProfileException):
        await AttendanceService(db_session).clock_out(owner["user"]["id"], org_id)
