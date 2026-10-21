"""Tests for POST /workflow-instances (M11 slice C): starting a case."""
from datetime import UTC, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from tests.tasks.test_tasks_router import AUDIT, AUTH, MEMBERSHIPS, NOTIFICATIONS, TASKS, _auth_header, _world
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create

INSTANCES = "/api/v1/workflow-instances"
LAGOS = ZoneInfo("Africa/Lagos")


async def _template(client, w, *steps) -> dict:
    """A template with the given steps, each (name, department_id, extra_fields)."""
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    for name, department_id, extra in steps:
        assert (await _add(client, w.hr, template["id"], name, department_id, **extra)).status_code == 200
    return template


async def _start(client, headers, template_id: str, subject: str = "Zenith Ltd"):
    return await client.post(INSTANCES, json={"template_id": template_id, "subject": subject}, headers=headers)


async def _tasks_of(client, w, instance_id: str) -> list[dict]:
    """The tasks a case has created, seen by HR (who sees every task)."""
    listed = await client.get(TASKS, params={"limit": 100}, headers=w.hr)
    return [t for t in listed.json()["data"] if t["workflow_instance_id"] == instance_id]


async def _titles(client, headers) -> list[str]:
    return [n["title"] for n in (await client.get(NOTIFICATIONS, headers=headers)).json()]


@pytest.mark.asyncio
async def test_an_employee_starts_a_case_and_only_the_first_step_gets_a_task(client, monkeypatch):
    """Chidi starts "Zenith Ltd": the case is in progress and just step 1's task exists, for the default assignee."""
    w = await _world(client, monkeypatch, "is1")
    template = await _template(
        client, w,
        ("Sales hand-off", w.sales, {"default_assignee_employee_id": w.dana.employee_id, "default_turnaround_hours": 24}),
        ("Finance review", w.dispatch, {}),
        ("Legal check", w.sales, {}),
    )

    started = await _start(client, w.chidi.h, template["id"])

    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "in_progress" and body["subject"] == "Zenith Ltd"
    assert body["workflow_template_id"] == template["id"] and body["started_by_user_id"] == w.chidi.user_id
    assert body["completed_at"] is None and body["cancel_reason"] is None
    tasks = await _tasks_of(client, w, body["id"])
    assert len(tasks) == 1
    task = tasks[0]
    assert task["title"] == "Sales hand-off: Zenith Ltd" and task["department_id"] == w.sales
    assert task["assigned_to_employee_id"] == w.dana.employee_id and task["status"] == "open"
    assert task["created_by_user_id"] is None
    assert 'Step 1 of 3 in "Client Onboarding"' in task["description"]
    assert "New task: Sales hand-off: Zenith Ltd" in await _titles(client, w.dana.h)


@pytest.mark.asyncio
async def test_the_first_tasks_deadline_is_in_business_hours(client, monkeypatch):
    """24 business hours lands inside a working weekday in Lagos, days ahead; no turnaround means no deadline."""
    w = await _world(client, monkeypatch, "is2")
    with_hours = await _template(client, w, ("Sales hand-off", w.sales, {"default_turnaround_hours": 24}))
    without_hours = await _template(client, w, ("Sales hand-off", w.sales, {}))

    timed = (await _start(client, w.chidi.h, with_hours["id"])).json()
    untimed = (await _start(client, w.chidi.h, without_hours["id"])).json()

    due = datetime.fromisoformat((await _tasks_of(client, w, timed["id"]))[0]["due_at"]).astimezone(LAGOS)
    assert due.weekday() < 5 and 9 <= due.hour <= 17
    # 24 business hours is three working days, a little over two plain days
    # at least and about five with a weekend in between.
    days_ahead = (due.astimezone(UTC) - datetime.now(UTC)).total_seconds() / 86400
    assert 2 < days_ahead < 6
    assert (await _tasks_of(client, w, untimed["id"]))[0]["due_at"] is None


@pytest.mark.asyncio
async def test_a_step_with_no_default_assignee_waits_in_the_queue_and_the_head_is_told(client, monkeypatch):
    """Dispatch's first step has nobody assigned: unassigned task, Tunde (head of Dispatch) is asked to assign it."""
    w = await _world(client, monkeypatch, "is3")
    template = await _template(client, w, ("Dispatch check", w.dispatch, {}))

    started = (await _start(client, w.chidi.h, template["id"])).json()

    task = (await _tasks_of(client, w, started["id"]))[0]
    assert task["assigned_to_employee_id"] is None
    assert "A task for Dispatch needs an owner" in await _titles(client, w.tunde.h)


@pytest.mark.asyncio
async def test_starting_is_audited(client, monkeypatch):
    """The audit log records who started which template for which subject."""
    w = await _world(client, monkeypatch, "is4")
    template = await _template(client, w, ("Sales hand-off", w.sales, {}))

    started = (await _start(client, w.chidi.h, template["id"], "  Acme Ltd ")).json()

    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_instance", "entity_id": started["id"]}, headers=w.hr
    )
    entry = audit.json()["data"][0]
    assert entry["action"] == "start" and entry["actor_user_id"] == w.chidi.user_id
    assert entry["changes"]["new"] == {
        "workflow_template_id": template["id"], "subject": "Acme Ltd", "status": "in_progress",
    }


@pytest.mark.asyncio
async def test_an_archived_deleted_unknown_or_empty_template_cannot_start_a_case(client, monkeypatch):
    """Archived: 409 by name. Deleted or unknown: 404. No steps: 422. Nothing is created in any case."""
    w = await _world(client, monkeypatch, "is5")
    archived = await _template(client, w, ("Sales hand-off", w.sales, {}))
    deleted = await _template(client, w, ("Sales hand-off", w.sales, {}))
    empty = await _create(client, w.hr, "No steps yet", w.dispatch)
    await client.post(f"{TEMPLATES}/{archived['id']}/archive", headers=w.hr)
    await client.delete(f"{TEMPLATES}/{deleted['id']}", headers=w.hr)

    on_archived = await _start(client, w.chidi.h, archived["id"])
    on_deleted = await _start(client, w.chidi.h, deleted["id"])
    on_unknown = await _start(client, w.chidi.h, "00000000-0000-0000-0000-000000000000")
    on_empty = await _start(client, w.chidi.h, empty["id"])

    assert on_archived.status_code == 409 and on_archived.json()["code"] == "WORKFLOW_TEMPLATE_ARCHIVED"
    assert on_deleted.status_code == 404 and on_unknown.status_code == 404
    assert on_unknown.json()["code"] == "WORKFLOW_TEMPLATE_NOT_FOUND"
    assert on_empty.status_code == 422 and "no steps" in on_empty.json()["message"]
    assert (await client.get(TASKS, params={"limit": 100}, headers=w.hr)).json()["data"] == []


@pytest.mark.asyncio
async def test_another_companys_template_is_a_404_and_a_blank_subject_a_422(client, monkeypatch):
    """Row-level security hides the other company's template; the subject must not be blank."""
    mine = await _world(client, monkeypatch, "is6")
    other = await _world(client, monkeypatch, "is7")
    theirs = await _template(client, other, ("Sales hand-off", other.sales, {}))
    own = await _template(client, mine, ("Sales hand-off", mine.sales, {}))

    foreign = await _start(client, mine.chidi.h, theirs["id"])
    blank = await _start(client, mine.chidi.h, own["id"], "   ")
    too_long = await _start(client, mine.chidi.h, own["id"], "x" * 201)

    assert foreign.status_code == 404
    assert blank.status_code == 422 and too_long.status_code == 422


@pytest.mark.asyncio
async def test_hr_may_start_without_an_employee_record_but_a_member_with_none_may_not(
    client, monkeypatch
):
    """The registering HR owner has no employee record and can start; an invited member with none gets a 403."""
    w = await _world(client, monkeypatch, "is8")
    template = await _template(client, w, ("Sales hand-off", w.sales, {}))
    outsider = await _member_without_employee(client, monkeypatch, w, "is8_outsider@example.com")

    by_hr = await _start(client, w.hr, template["id"])
    by_outsider = await _start(client, outsider, template["id"])

    assert by_hr.status_code == 200
    assert by_outsider.status_code == 403 and "employees" in by_outsider.json()["message"]


async def _member_without_employee(client, monkeypatch, w, email: str) -> dict:
    """Invite and accept a teammate, but give them no employee record."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(MEMBERSHIPS, json={"email": email, "role": "employee"}, headers=w.hr)
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accepted = (await client.post(
        f"{AUTH}/accept-invite",
        json={"token": token, "full_name": "Outsider Tester", "password": "Password123#",
              "confirm_password": "Password123#"},
    )).json()
    return _auth_header(accepted["access_token"])
