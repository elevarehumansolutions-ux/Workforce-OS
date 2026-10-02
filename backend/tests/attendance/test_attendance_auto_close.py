"""Tests for the nightly attendance auto-close.

Covers the cross-tenant lookup (and that it reveals nothing else), the close
itself against a fixed clock, organization timezones, idempotency, the
audit trail and in-app notifications, and the Celery wiring.
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select, text

from app.core.celery_app import celery
from app.modules.attendance import tasks as attendance_tasks
from app.modules.attendance.models import AttendanceRecord
from app.modules.attendance.repository import AttendanceRepository
from app.modules.attendance.service import AttendanceService
from tests.conftest import register_verified_and_login, set_org_context

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"
BUSINESS_DNA = "/api/v1/business-dna"
NOTIFICATIONS = "/api/v1/notifications"
AUDIT = "/api/v1/audit-log"
AUTH = "/api/v1/auth"

# 11:00 in Lagos (UTC+1) on 2 October 2026: that day's midnight was 23:00 UTC on 1 October.
NOW = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
LAGOS_MIDNIGHT = datetime(2026, 10, 1, 23, 0, tzinfo=UTC)


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org(client, email: str) -> tuple[dict, dict, str]:
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "Officer"}, headers=h
    )
    return owner, h, pos.json()["id"]


async def _employee(client, h, position_id, email, user_id=None, manager_id=None) -> str:
    body = {
        "position_id": position_id, "first_name": "Test", "last_name": email.split("@")[0],
        "work_email": email, "start_date": "2026-01-01",
    }
    if user_id:
        body["user_id"] = user_id
    if manager_id:
        body["manager_id"] = manager_id
    return (await client.post(EMPLOYEES, json=body, headers=h)).json()["id"]


async def _manager_user(client, monkeypatch, h, email: str) -> dict:
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(MEMBERSHIPS, json={"email": email, "role": "manager"}, headers=h)
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    resp = await client.post(
        f"{AUTH}/accept-invite",
        json={"token": token, "full_name": "Test Manager", "password": "Password123#",
              "confirm_password": "Password123#"},
    )
    return resp.json()


async def _record(db_session, employee_id):
    return (await db_session.execute(
        select(AttendanceRecord).where(AttendanceRecord.employee_id == employee_id)
    )).scalar_one()


@pytest.mark.asyncio
async def test_the_cross_tenant_lookup_returns_only_orgs_with_someone_clocked_in(client, db_session):
    """It finds the org (and its timezone) that has an open record, and not one that doesn't."""
    owner, h, pos = await _org(client, "att_ac1@example.com")
    quiet_owner, quiet_h, quiet_pos = await _org(client, "att_ac1b@example.com")
    org_id = owner["organization"]["id"]
    employee = await _employee(client, h, pos, "att_ac1@example.com", owner["user"]["id"])
    await set_org_context(db_session, org_id)
    await AttendanceRepository(db_session).create_open_record(org_id, employee, NOW)

    # A session scoped to some unrelated tenant can't see this org's attendance directly...
    await set_org_context(db_session, uuid.uuid4())
    direct = await db_session.execute(select(func.count()).select_from(AttendanceRecord))
    assert direct.scalar_one() == 0
    # ...but the narrow function still reports which orgs have someone clocked in.
    found = dict(await AttendanceRepository(db_session).list_organizations_with_open_records())

    assert found[uuid.UUID(org_id)] == "Africa/Lagos"
    assert uuid.UUID(quiet_owner["organization"]["id"]) not in found


@pytest.mark.asyncio
async def test_the_app_role_still_cannot_bypass_row_level_security(db_session):
    """The escape hatch is one narrow function; the app's own role gained nothing."""
    result = await db_session.execute(
        text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
    )
    row = result.one()
    assert (row.rolbypassrls, row.rolsuper) == (False, False)


@pytest.mark.asyncio
async def test_it_closes_yesterdays_open_record_at_the_organizations_midnight_and_spares_todays(client, db_session):
    """Stale -> closed at the Lagos midnight as 'system'; clocked in today -> untouched."""
    owner, h, pos = await _org(client, "att_ac2@example.com")
    org_id = owner["organization"]["id"]
    stale_emp = await _employee(client, h, pos, "stale@att-ac2.example.com")
    today_emp = await _employee(client, h, pos, "today@att-ac2.example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    await repo.create_open_record(org_id, stale_emp, datetime(2026, 10, 1, 8, 0, tzinfo=UTC))
    await repo.create_open_record(org_id, today_emp, datetime(2026, 10, 2, 8, 0, tzinfo=UTC))

    closed = await AttendanceService(db_session).auto_close_stale_records(org_id, NOW)

    assert closed == 1
    stale = await _record(db_session, stale_emp)
    assert stale.clock_out_at == LAGOS_MIDNIGHT
    assert stale.closed_by == "system"
    assert stale.close_reason == "Did not clock out"
    today = await _record(db_session, today_emp)
    assert today.clock_out_at is None and today.closed_by is None


@pytest.mark.asyncio
async def test_running_it_again_closes_nothing_more(client, db_session):
    """Idempotent: a retry or a second hourly run is harmless, and notifies nobody twice."""
    owner, h, pos = await _org(client, "att_ac3@example.com")
    org_id = owner["organization"]["id"]
    emp = await _employee(client, h, pos, "att_ac3@example.com", owner["user"]["id"])
    await set_org_context(db_session, org_id)
    await AttendanceRepository(db_session).create_open_record(
        org_id, emp, datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    )
    service = AttendanceService(db_session)

    first = await service.auto_close_stale_records(org_id, NOW)
    second = await service.auto_close_stale_records(org_id, NOW)

    assert (first, second) == (1, 0)
    notes = await client.get(NOTIFICATIONS, headers=h)
    assert len([n for n in notes.json() if n["title"] == "You were clocked out automatically"]) == 1


@pytest.mark.asyncio
async def test_midnight_is_the_organizations_not_utcs(client, db_session):
    """The same moment is 'yesterday' for one timezone's open record and 'today' for another's."""
    owner, h, pos = await _org(client, "att_ac4@example.com")
    org_id = owner["organization"]["id"]
    await client.put(BUSINESS_DNA, json={"timezone": "Pacific/Auckland"}, headers=h)  # UTC+13 in October
    early = await _employee(client, h, pos, "early@att-ac4.example.com")
    late = await _employee(client, h, pos, "late@att-ac4.example.com")
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    await repo.create_open_record(org_id, early, datetime(2026, 10, 1, 8, 0, tzinfo=UTC))   # 2 Oct 21:00 NZ... before midnight
    await repo.create_open_record(org_id, late, datetime(2026, 10, 1, 12, 0, tzinfo=UTC))   # 2 Oct 01:00 NZ: already "today"

    closed = await AttendanceService(db_session).auto_close_stale_records(org_id, NOW)

    assert closed == 1
    assert (await _record(db_session, early)).clock_out_at == datetime(2026, 10, 1, 11, 0, tzinfo=UTC)
    assert (await _record(db_session, late)).clock_out_at is None


@pytest.mark.asyncio
async def test_the_employee_and_their_manager_are_notified_and_the_close_is_audited(client, monkeypatch, db_session):
    """In-app notifications for both, and an audit entry with no human actor."""
    owner, h, pos = await _org(client, "att_ac5@example.com")
    org_id = owner["organization"]["id"]
    manager = await _manager_user(client, monkeypatch, h, "att_ac5_mgr@example.com")
    manager_employee = await _employee(client, h, pos, "att_ac5_mgr@example.com", manager["user"]["id"])
    worker = await _employee(client, h, pos, "att_ac5@example.com", owner["user"]["id"], manager_employee)
    await set_org_context(db_session, org_id)
    await AttendanceRepository(db_session).create_open_record(
        org_id, worker, datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    )

    await AttendanceService(db_session).auto_close_stale_records(org_id, NOW)

    mine = (await client.get(NOTIFICATIONS, headers=h)).json()
    theirs = (await client.get(NOTIFICATIONS, headers=_auth_header(manager["access_token"]))).json()
    mine_one = [n for n in mine if n["title"] == "You were clocked out automatically"]
    theirs_one = [n for n in theirs if "didn't clock out" in n["title"]]
    assert len(mine_one) == 1 and mine_one[0]["category"] == "system"
    assert "Africa/Lagos" in mine_one[0]["body"]
    assert len(theirs_one) == 1
    audit = (await client.get(AUDIT, params={"entity_type": "attendance_record"}, headers=h)).json()["data"]
    auto = [e for e in audit if e["action"] == "auto_close"]
    assert len(auto) == 1
    assert auto[0]["actor_user_id"] is None
    assert auto[0]["changes"]["new"]["closed_by"] == "system"


@pytest.mark.asyncio
async def test_someone_who_already_clocked_out_is_left_alone(client, db_session):
    """A real clock-out is never overwritten by the system's estimate."""
    owner, h, pos = await _org(client, "att_ac6@example.com")
    org_id = owner["organization"]["id"]
    emp = await _employee(client, h, pos, "att_ac6@example.com", owner["user"]["id"])
    await set_org_context(db_session, org_id)
    repo = AttendanceRepository(db_session)
    clock_in = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    await repo.create_open_record(org_id, emp, clock_in)
    real_out = datetime(2026, 10, 1, 16, 30, tzinfo=UTC)
    from app.modules.attendance.enums import AttendanceClosedBy
    await repo.close_open_record(emp, real_out, AttendanceClosedBy.EMPLOYEE)

    closed = await AttendanceService(db_session).auto_close_stale_records(org_id, NOW)

    assert closed == 0
    row = await _record(db_session, emp)
    assert row.clock_out_at == real_out and row.closed_by == "employee"


@pytest.mark.asyncio
async def test_the_scan_enqueues_one_task_per_organization_with_someone_clocked_in(client, db_session, monkeypatch):
    """The hourly scan fans out by organization, by task name."""
    owner, h, pos = await _org(client, "att_ac7@example.com")
    org_id = owner["organization"]["id"]
    emp = await _employee(client, h, pos, "att_ac7@example.com", owner["user"]["id"])
    await set_org_context(db_session, org_id)
    await AttendanceRepository(db_session).create_open_record(org_id, emp, NOW)
    sent = MagicMock()
    monkeypatch.setattr(celery, "send_task", sent)

    count = await attendance_tasks.run_auto_close_scan(db_session)

    assert count >= 1
    enqueued = {
        call.kwargs["args"][0]
        for call in sent.call_args_list
        if call.args[0] == attendance_tasks.AUTO_CLOSE_ORG_TASK
    }
    assert org_id in enqueued


@pytest.mark.asyncio
async def test_the_per_organization_task_sets_its_own_context_and_commits(client, db_session):
    """run_auto_close_for_organization needs no request: it closes under the org's context."""
    owner, h, pos = await _org(client, "att_ac8@example.com")
    org_id = owner["organization"]["id"]
    emp = await _employee(client, h, pos, "att_ac8@example.com", owner["user"]["id"])
    await set_org_context(db_session, org_id)
    await AttendanceRepository(db_session).create_open_record(
        org_id, emp, datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    )

    closed = await attendance_tasks.run_auto_close_for_organization(db_session, uuid.UUID(org_id), NOW)

    assert closed == 1


def test_the_tasks_are_registered_and_scheduled_under_the_names_in_the_code():
    """A renamed task would silently stop running; pin the names the Beat schedule points at."""
    assert attendance_tasks.AUTO_CLOSE_TASK in celery.tasks
    assert attendance_tasks.AUTO_CLOSE_ORG_TASK in celery.tasks
    assert celery.tasks[attendance_tasks.AUTO_CLOSE_TASK].name == attendance_tasks.AUTO_CLOSE_TASK
    assert celery.conf.beat_schedule["attendance-auto-close"]["task"] == attendance_tasks.AUTO_CLOSE_TASK
