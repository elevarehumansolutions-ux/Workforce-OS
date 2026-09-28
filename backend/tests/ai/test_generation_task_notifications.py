"""HR admins get notified when a run actually creates suggestions.

Scenario: Adaeze's org has two HR administrators, an employee, and one HR
administrator who was later deactivated. A run finds one critical
position — both active HR admins should see a notification; the employee
and the deactivated admin should not.
"""
import uuid

import pytest
from sqlalchemy import select

from tests.ai.test_generation_task import _critical_position_only
from tests.ai.test_llm_generate_structured import _by_output_format, _fake_anthropic, _usage
from tests.audit_and_notification.test_audit_log import _invite_and_accept
from tests.conftest import register_verified_and_login, set_org_context
from app.modules.audit_and_notification.models import Notification
from app.modules.ai.schemas import CriticalPositionAnswer, MissingDepartmentAnswer, RevenueAllocationAnswer
from app.modules.ai.tasks import run_generation

MEMBERSHIPS = "/api/v1/memberships"
DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _seed_org(client, db_session, email):
    """The founder (an HR admin) plus one critical department with one position."""
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post(DEPARTMENTS, json={"name": "Operations", "is_critical": True}, headers=h)
    await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "Dispatcher"}, headers=h)
    await set_org_context(db_session, org_id)
    return owner, h, org_id


async def _notified_user_ids(db_session, org_id):
    rows = (
        await db_session.scalars(select(Notification).where(Notification.organization_id == org_id))
    ).all()
    return {row.recipient_user_id for row in rows}


@pytest.mark.asyncio
async def test_active_hr_admins_are_notified_others_are_not(client, db_session, monkeypatch):
    """Two HR admins notified; an employee and a deactivated HR admin are not."""
    owner, h, org_id = await _seed_org(client, db_session, "notify1@example.com")
    second_admin = await _invite_and_accept(client, monkeypatch, owner, "notify1b@example.com", "hr_administrator")
    employee = await _invite_and_accept(client, monkeypatch, owner, "notify1c@example.com", "employee")
    deactivated_admin = await _invite_and_accept(client, monkeypatch, owner, "notify1d@example.com", "hr_administrator")

    memberships = (await client.get(MEMBERSHIPS, headers=h)).json()["data"]
    deactivated_membership_id = next(
        m["id"] for m in memberships if m["user"]["email"] == "notify1d@example.com"
    )
    await client.patch(
        f"{MEMBERSHIPS}/{deactivated_membership_id}", json={"is_deactivated": True}, headers=h
    )
    await set_org_context(db_session, org_id)
    # Operations is critical, so this run also makes a revenue-allocation
    # call — give it an empty answer so the assertions below (which are
    # about the notification, not about how many suggestions exist) stay
    # exactly "1 created".
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_critical_position_only(["P1"]))

    # A SAVEPOINT, so run_generation's own commit() doesn't end this test's
    # outer transaction — see 08_DECISIONS.md 2026-09-27 (test-hygiene gap).
    async with db_session.begin_nested():
        created_count = await run_generation(db_session, org_id)

    assert created_count == 1
    notified = await _notified_user_ids(db_session, org_id)
    assert notified == {uuid.UUID(owner["user"]["id"]), uuid.UUID(second_admin["user"]["id"])}
    assert uuid.UUID(employee["user"]["id"]) not in notified
    assert uuid.UUID(deactivated_admin["user"]["id"]) not in notified


@pytest.mark.asyncio
async def test_no_suggestions_created_means_no_notification(client, db_session, monkeypatch):
    """A run that finds nothing worth suggesting shouldn't tell anyone it did."""
    owner, h, org_id = await _seed_org(client, db_session, "notify2@example.com")
    _fake_anthropic(
        monkeypatch,
        usage=_usage(),
        parsed_output=_by_output_format(
            {
                CriticalPositionAnswer: CriticalPositionAnswer(picks=[]),
                RevenueAllocationAnswer: RevenueAllocationAnswer(picks=[]),
                MissingDepartmentAnswer: MissingDepartmentAnswer(picks=[]),
            }
        ),
    )

    async with db_session.begin_nested():
        created_count = await run_generation(db_session, org_id)

    assert created_count == 0
    assert await _notified_user_ids(db_session, org_id) == set()
