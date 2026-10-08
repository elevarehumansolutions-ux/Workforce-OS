"""Repository-level tests for AttendanceRepository.

Seeds ``attendance_records`` rows directly and checks the repository's
reads against the real database, including the row-level security that keeps
one organization's records invisible to another.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.attendance.enums import AttendanceClosedBy
from app.modules.attendance.models import AttendanceRecord
from app.modules.attendance.repository import AttendanceRepository
from tests.conftest import register_verified_and_login, set_org_context

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org_with_two_employees(client, email: str) -> tuple[str, str, str]:
    """Create an org and two employees; returns (organization_id, first_id, second_id)."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "Officer"}, headers=h
    )
    ids = []
    for n in (1, 2):
        emp = await client.post(
            EMPLOYEES,
            json={
                "position_id": pos.json()["id"],
                "first_name": f"Person{n}",
                "last_name": "Test",
                "work_email": f"person{n}.{email}",
                "start_date": "2026-01-01",
            },
            headers=h,
        )
        ids.append(emp.json()["id"])
    return owner["organization"]["id"], ids[0], ids[1]


def _record(organization_id, employee_id, hours_ago: int, closed: bool) -> AttendanceRecord:
    clock_in = datetime.now(UTC) - timedelta(hours=hours_ago)
    return AttendanceRecord(
        organization_id=organization_id,
        employee_id=employee_id,
        clock_in_at=clock_in,
        clock_out_at=clock_in + timedelta(hours=1) if closed else None,
        closed_by="employee" if closed else None,
    )


@pytest.mark.asyncio
async def test_get_open_record_is_none_when_the_employee_has_no_records(client, db_session):
    """Someone who has never clocked in is not clocked in."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo1@example.com")
    await set_org_context(db_session, org_id)

    assert await AttendanceRepository(db_session).get_open_record(first) is None


@pytest.mark.asyncio
async def test_get_open_record_returns_the_open_one_not_the_closed_history(client, db_session):
    """Past closed records don't count; only the record with no clock-out does."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo2@example.com")
    await set_org_context(db_session, org_id)
    old = _record(org_id, first, hours_ago=72, closed=True)
    open_one = _record(org_id, first, hours_ago=2, closed=False)
    db_session.add_all([old, open_one])
    await db_session.flush()

    found = await AttendanceRepository(db_session).get_open_record(first)

    assert found is not None
    assert found.id == open_one.id
    assert found.clock_out_at is None


@pytest.mark.asyncio
async def test_get_open_record_is_none_once_everything_is_closed(client, db_session):
    """After clocking out there is nothing open."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo3@example.com")
    await set_org_context(db_session, org_id)
    db_session.add(_record(org_id, first, hours_ago=10, closed=True))
    await db_session.flush()

    assert await AttendanceRepository(db_session).get_open_record(first) is None


@pytest.mark.asyncio
async def test_get_open_record_only_looks_at_that_employee(client, db_session):
    """One employee being clocked in says nothing about their colleague."""
    org_id, first, second = await _org_with_two_employees(client, "att_repo4@example.com")
    await set_org_context(db_session, org_id)
    db_session.add(_record(org_id, first, hours_ago=1, closed=False))
    await db_session.flush()
    repo = AttendanceRepository(db_session)

    assert await repo.get_open_record(first) is not None
    assert await repo.get_open_record(second) is None


@pytest.mark.asyncio
async def test_get_open_record_cannot_see_another_organizations_records(client, db_session):
    """Row-level security hides an open record from a session scoped to a different org."""
    org_a, first, _ = await _org_with_two_employees(client, "att_repo5a@example.com")
    org_b, _, _ = await _org_with_two_employees(client, "att_repo5b@example.com")
    await set_org_context(db_session, org_a)
    db_session.add(_record(org_a, first, hours_ago=1, closed=False))
    await db_session.flush()
    repo = AttendanceRepository(db_session)
    assert await repo.get_open_record(first) is not None

    await set_org_context(db_session, org_b)

    assert await repo.get_open_record(first) is None


@pytest.mark.asyncio
async def test_create_open_record_makes_an_open_record_that_get_open_record_finds(client, db_session):
    """Clocking in creates a row with a clock-in time and all three close fields empty."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo6@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    clock_in = datetime.now(UTC)

    created = await repo.create_open_record(org_id, first, clock_in)

    assert created.id is not None
    assert created.created_at is not None
    assert created.clock_out_at is None
    assert created.closed_by is None
    assert created.close_reason is None
    found = await repo.get_open_record(first)
    assert found is not None and found.id == created.id


@pytest.mark.asyncio
async def test_a_second_open_record_for_the_same_employee_is_absorbed_not_inserted(client, db_session):
    """INSERT ... ON CONFLICT DO NOTHING: the second call returns None and adds no row."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo7@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    original = await repo.create_open_record(org_id, first, datetime.now(UTC))

    second = await repo.create_open_record(org_id, first, datetime.now(UTC))

    assert second is None
    found = await repo.get_open_record(first)
    assert found is not None and found.id == original.id
    count = await db_session.execute(
        select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.employee_id == first)
    )
    assert count.scalar_one() == 1


@pytest.mark.asyncio
async def test_two_employees_can_each_be_clocked_in_at_the_same_time(client, db_session):
    """The one-open-record rule is per employee, not per organization."""
    org_id, first, second = await _org_with_two_employees(client, "att_repo8@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)

    a = await repo.create_open_record(org_id, first, datetime.now(UTC))
    b = await repo.create_open_record(org_id, second, datetime.now(UTC))

    assert a.id != b.id


@pytest.mark.asyncio
async def test_close_open_record_by_the_employee_sets_the_three_fields_together(client, db_session):
    """An employee clock-out records the time and who did it, with no reason."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo9@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    clock_in = datetime.now(UTC) - timedelta(hours=8)
    await repo.create_open_record(org_id, first, clock_in)
    clock_out = clock_in + timedelta(hours=8)

    closed = await repo.close_open_record(first, clock_out, AttendanceClosedBy.EMPLOYEE)

    assert closed is not None
    assert closed.clock_out_at == clock_out
    assert closed.closed_by == "employee"
    assert closed.close_reason is None
    assert await repo.get_open_record(first) is None


@pytest.mark.asyncio
async def test_close_open_record_by_the_system_keeps_the_reason(client, db_session):
    """An auto-close is marked 'system' and says why, so it can be told apart from a real clock-out."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo10@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    clock_in = datetime.now(UTC) - timedelta(hours=15)
    await repo.create_open_record(org_id, first, clock_in)

    closed = await repo.close_open_record(
        first, clock_in + timedelta(hours=14), AttendanceClosedBy.SYSTEM, "Did not clock out"
    )

    assert closed is not None
    assert closed.closed_by == "system"
    assert closed.close_reason == "Did not clock out"


@pytest.mark.asyncio
async def test_closing_a_record_frees_the_slot_for_the_next_clock_in(client, db_session):
    """After Monday is closed, Tuesday's open record is allowed."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo11@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    monday = datetime.now(UTC) - timedelta(days=1)
    record = await repo.create_open_record(org_id, first, monday)
    await repo.close_open_record(first, monday + timedelta(hours=8), AttendanceClosedBy.EMPLOYEE)

    tuesday = await repo.create_open_record(org_id, first, datetime.now(UTC))

    assert tuesday.id != record.id
    found = await repo.get_open_record(first)
    assert found is not None and found.id == tuesday.id


@pytest.mark.asyncio
async def test_a_clock_out_earlier_than_the_clock_in_is_clamped_to_zero_length(client, db_session):
    """A clock running slightly behind never produces negative hours: the record closes at its clock-in time."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo12@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    clock_in = datetime.now(UTC)
    await repo.create_open_record(org_id, first, clock_in)

    closed = await repo.close_open_record(first, clock_in - timedelta(hours=1), AttendanceClosedBy.EMPLOYEE)

    assert closed is not None
    assert closed.clock_out_at == clock_in


@pytest.mark.asyncio
async def test_close_open_record_returns_none_when_nothing_is_open(client, db_session):
    """No open record means nothing to close: None, not an error."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo13@example.com")
    await set_org_context(db_session, org_id)

    assert await AttendanceRepository(db_session).close_open_record(
        first, datetime.now(UTC), AttendanceClosedBy.EMPLOYEE
    ) is None


@pytest.mark.asyncio
async def test_a_second_close_changes_nothing_and_the_first_clock_out_time_stands(client, db_session):
    """Two clock-outs in a row: the second matches no open record, so it cannot overwrite the first."""
    org_id, first, _ = await _org_with_two_employees(client, "att_repo14@example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    clock_in = datetime.now(UTC) - timedelta(hours=9)
    await repo.create_open_record(org_id, first, clock_in)
    first_out = clock_in + timedelta(hours=8)
    await repo.close_open_record(first, first_out, AttendanceClosedBy.EMPLOYEE)

    second = await repo.close_open_record(first, first_out + timedelta(hours=1), AttendanceClosedBy.SYSTEM, "late")

    assert second is None
    row = (await db_session.execute(
        select(AttendanceRecord).where(AttendanceRecord.employee_id == first)
    )).scalar_one()
    assert row.clock_out_at == first_out
    assert row.closed_by == "employee"
