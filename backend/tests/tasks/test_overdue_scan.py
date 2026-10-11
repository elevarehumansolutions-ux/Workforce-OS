"""Tests for the overdue scan (M10 slice D): who is told, once, and when.

Same company as the other task tests: Tunde heads Dispatch, Chidi and Bola work
there, Dana and Sam are managers (Sam in Sales, which has no head), Adaeze is HR.
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, text

from app.core.celery_app import celery
from app.modules.audit_and_notification.models import Notification
from app.modules.tasks import tasks as task_jobs
from app.modules.tasks.repository import TaskRepository
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import NOTIFICATIONS, TASKS, _clock_in, _task, _world

LONG_AGO = "2020-01-01T00:00:00+00:00"
ANOTHER_LONG_AGO = "2021-01-01T00:00:00+00:00"
FAR_AHEAD = "2099-01-01T00:00:00+00:00"


async def _run_scan_for(db_session, world) -> int:
    """Run the per-organization announcement job the way Celery would."""
    org_id = world.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    return await task_jobs.run_announce_for_organization(
        db_session, uuid.UUID(org_id), datetime.now(UTC)
    )


async def _overdue_titles(client, headers) -> list[str]:
    """The 'Task overdue: ...' notifications a person has received."""
    resp = await client.get(NOTIFICATIONS, headers=headers)
    return [n["title"] for n in resp.json() if n["title"].startswith("Task overdue")]


async def _prompts(client, headers) -> list[str]:
    """The 'Was something holding up ...?' invitations a person has received."""
    resp = await client.get(NOTIFICATIONS, headers=headers)
    return [n["title"] for n in resp.json() if n["title"].startswith("Was something holding up")]


@pytest.mark.asyncio
async def test_the_assignee_is_invited_to_explain_the_delay_and_nobody_else_is(client, monkeypatch, db_session):
    """Chidi gets the 'was something holding it up?' note; Tunde and HR only get the plain overdue alert."""
    w = await _world(client, monkeypatch, "d14")
    await _task(client, w.hr, w.dispatch, "Fix route", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)

    await _run_scan_for(db_session, w)

    assert await _prompts(client, w.chidi.h) == ["Was something holding up: Fix route?"]
    assert await _prompts(client, w.tunde.h) == []
    assert await _prompts(client, w.hr) == []
    assert await _overdue_titles(client, w.chidi.h) == ["Task overdue: Fix route"]      # the alert still goes out


@pytest.mark.asyncio
async def test_no_invitation_when_the_assignee_has_already_recorded_a_block_or_nobody_is_assigned(
    client, monkeypatch, db_session
):
    """Don't nag someone who already explained, and there is no one to invite on an unassigned task."""
    w = await _world(client, monkeypatch, "d15")
    await _clock_in(client, w.chidi)
    explained = (await _task(client, w.hr, w.dispatch, "Explained", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)).json()["id"]
    await client.post(
        f"{TASKS}/{explained}/block", json={"category": "other", "reason": "Waiting on a supplier"}, headers=w.chidi.h
    )
    await client.post(f"{TASKS}/{explained}/unblock", headers=w.chidi.h)      # a block exists, the task is overdue again
    await _task(client, w.hr, w.dispatch, "Unassigned", due_at=LONG_AGO)

    announced = await _run_scan_for(db_session, w)

    assert announced == 2                                      # both are announced to the head...
    assert await _prompts(client, w.chidi.h) == []             # ...but nobody is invited to explain
    assert sorted(await _overdue_titles(client, w.tunde.h)) == ["Task overdue: Explained", "Task overdue: Unassigned"]


@pytest.mark.asyncio
async def test_the_assignee_and_the_department_head_are_told_and_nobody_else(client, monkeypatch, db_session):
    """Chidi's task goes overdue: Chidi and Tunde (head of Dispatch) hear about it. Bola and Dana do not."""
    w = await _world(client, monkeypatch, "d1")
    await _task(client, w.hr, w.dispatch, "Fix route", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)

    announced = await _run_scan_for(db_session, w)

    assert announced == 1
    assert await _overdue_titles(client, w.chidi.h) == ["Task overdue: Fix route"]
    assert await _overdue_titles(client, w.tunde.h) == ["Task overdue: Fix route"]
    assert await _overdue_titles(client, w.bola.h) == []
    assert await _overdue_titles(client, w.dana.h) == []
    assert await _overdue_titles(client, w.hr) == []        # the department has a head, so HR isn't bothered


@pytest.mark.asyncio
async def test_each_overdue_task_is_announced_only_once(client, monkeypatch, db_session):
    """The scan runs every few minutes; running it again must not repeat the alert."""
    w = await _world(client, monkeypatch, "d2")
    await _task(client, w.hr, w.dispatch, "Fix route", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)

    first = await _run_scan_for(db_session, w)
    second = await _run_scan_for(db_session, w)

    assert (first, second) == (1, 0)
    assert len(await _overdue_titles(client, w.chidi.h)) == 1
    assert len(await _overdue_titles(client, w.tunde.h)) == 1


@pytest.mark.asyncio
async def test_finished_cancelled_future_and_deadline_free_tasks_are_never_announced(client, monkeypatch, db_session):
    """Only an unfinished task with a deadline in the past counts."""
    w = await _world(client, monkeypatch, "d3")
    done = (await _task(client, w.hr, w.dispatch, "Done", due_at=LONG_AGO)).json()["id"]
    cancelled = (await _task(client, w.hr, w.dispatch, "Cancelled", due_at=LONG_AGO)).json()["id"]
    await _task(client, w.hr, w.dispatch, "Not due yet", due_at=FAR_AHEAD)
    await _task(client, w.hr, w.dispatch, "No deadline")
    await client.post(f"{TASKS}/{done}/complete", headers=w.hr)
    await client.post(f"{TASKS}/{cancelled}/cancel", json={"reason": "Not needed"}, headers=w.hr)

    announced = await _run_scan_for(db_session, w)

    assert announced == 0
    assert await _overdue_titles(client, w.tunde.h) == []


@pytest.mark.asyncio
async def test_with_no_department_head_the_hr_administrators_are_told(client, monkeypatch, db_session):
    """Sales has no head: Sam's overdue task is announced to Sam and to HR, so someone is accountable."""
    w = await _world(client, monkeypatch, "d4")
    await _task(client, w.hr, w.sales, "Quote for Acme", assigned_to_employee_id=w.sam.employee_id, due_at=LONG_AGO)

    await _run_scan_for(db_session, w)

    assert await _overdue_titles(client, w.sam.h) == ["Task overdue: Quote for Acme"]
    assert await _overdue_titles(client, w.hr) == ["Task overdue: Quote for Acme"]
    assert await _overdue_titles(client, w.tunde.h) == []     # heads a different department


@pytest.mark.asyncio
async def test_an_unassigned_overdue_task_is_announced_to_the_head(client, monkeypatch, db_session):
    """Nobody owns it yet, so the head (who must assign it) is the one told."""
    w = await _world(client, monkeypatch, "d5")
    await _task(client, w.hr, w.dispatch, "Orphan", due_at=LONG_AGO)

    await _run_scan_for(db_session, w)

    assert await _overdue_titles(client, w.tunde.h) == ["Task overdue: Orphan"]
    assert await _overdue_titles(client, w.chidi.h) == []


@pytest.mark.asyncio
async def test_a_head_who_is_also_the_assignee_gets_one_notification_not_two(client, monkeypatch, db_session):
    """Nobody is listed twice."""
    w = await _world(client, monkeypatch, "d6")
    await _task(client, w.hr, w.dispatch, "Tunde's own", assigned_to_employee_id=w.tunde.employee_id, due_at=LONG_AGO)

    await _run_scan_for(db_session, w)

    assert await _overdue_titles(client, w.tunde.h) == ["Task overdue: Tunde's own"]


@pytest.mark.asyncio
async def test_an_offboarded_assignee_is_not_told_but_the_head_still_is(client, monkeypatch, db_session):
    """Someone who has left shouldn't get alerts; the head needs to know the task is stuck."""
    w = await _world(client, monkeypatch, "d7")
    await _task(client, w.hr, w.dispatch, "Left behind", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)
    await client.post(f"/api/v1/employees/{w.chidi.employee_id}/offboard", headers=w.hr)

    await _run_scan_for(db_session, w)

    # Chidi can no longer log in to read his notifications, so look at the table itself.
    chidi_rows = await db_session.execute(
        select(Notification).where(Notification.recipient_user_id == uuid.UUID(w.chidi.user_id))
    )
    chidi_overdue = [n for n in chidi_rows.scalars() if n.title.startswith("Task overdue")]
    assert chidi_overdue == []
    assert await _overdue_titles(client, w.tunde.h) == ["Task overdue: Left behind"]


@pytest.mark.asyncio
async def test_the_lookup_finds_only_organizations_with_unannounced_overdue_tasks(client, monkeypatch, db_session):
    """It reports the busy org, not a quiet one, and stops reporting an org once it is announced."""
    busy = await _world(client, monkeypatch, "d9")
    quiet = await _world(client, monkeypatch, "d10")
    await _task(client, busy.hr, busy.dispatch, "Late", due_at=LONG_AGO)
    await _task(client, quiet.hr, quiet.dispatch, "Fine", due_at=FAR_AHEAD)
    busy_id = uuid.UUID(busy.owner["organization"]["id"])
    quiet_id = uuid.UUID(quiet.owner["organization"]["id"])
    repo = TaskRepository(db_session)

    await set_org_context(db_session, uuid.uuid4())     # no tenant of its own, like the real scan
    before = await repo.list_organizations_needing_scan()
    await _run_scan_for(db_session, busy)
    await set_org_context(db_session, uuid.uuid4())
    after = await repo.list_organizations_needing_scan()

    assert busy_id in before and quiet_id not in before
    assert busy_id not in after


@pytest.mark.asyncio
async def test_blocked_and_extended_tasks_are_not_announced_and_do_not_wake_the_scan(client, monkeypatch, db_session):
    """A blocked task, or one whose approved time covers the delay, is not announced; its org is not even queued."""
    quiet = await _world(client, monkeypatch, "d12")
    org_id = uuid.UUID(quiet.owner["organization"]["id"])
    blocked = (await _task(client, quiet.hr, quiet.dispatch, "Blocked", due_at=LONG_AGO)).json()["id"]
    extended = (await _task(client, quiet.hr, quiet.dispatch, "Extended", due_at=LONG_AGO)).json()["id"]
    await set_org_context(db_session, org_id)
    await db_session.execute(text("UPDATE tasks SET blocked_since = now() WHERE id = :id"), {"id": blocked})
    # About 63 years of approved time, so the real deadline is far in the future.
    await db_session.execute(
        text("UPDATE tasks SET approved_blocked_seconds = 2000000000 WHERE id = :id"), {"id": extended}
    )

    await set_org_context(db_session, uuid.uuid4())      # the real scan has no tenant of its own
    found = await TaskRepository(db_session).list_organizations_needing_scan()
    announced = await _run_scan_for(db_session, quiet)

    assert org_id not in found
    assert announced == 0
    assert await _overdue_titles(client, quiet.tunde.h) == []


@pytest.mark.asyncio
async def test_a_task_announced_while_overdue_can_be_announced_again_after_time_is_approved(
    client, monkeypatch, db_session
):
    """Approving blocked time moves the deadline, so the mark is cleared and the new moment gets its alert."""
    w = await _world(client, monkeypatch, "d13")
    org_id = w.owner["organization"]["id"]
    tid = (await _task(client, w.hr, w.dispatch, "Slipped", due_at=LONG_AGO)).json()["id"]
    first = await _run_scan_for(db_session, w)
    await set_org_context(db_session, org_id)
    await TaskRepository(db_session).add_approved_seconds(uuid.UUID(tid), 60)     # a reviewer approved a minute
    again = await _run_scan_for(db_session, w)                                    # still overdue, new deadline passed

    assert (first, again) == (1, 1)
    assert len(await _overdue_titles(client, w.tunde.h)) == 2


@pytest.mark.asyncio
async def test_the_scan_queues_one_job_per_organization_that_needs_one(client, monkeypatch, db_session):
    """The scheduled task fans out by organization, using the task name Celery knows."""
    w = await _world(client, monkeypatch, "d11")
    await _task(client, w.hr, w.dispatch, "Late", due_at=LONG_AGO)
    sent = MagicMock()
    monkeypatch.setattr(celery, "send_task", sent)
    await set_org_context(db_session, uuid.uuid4())

    count = await task_jobs.run_overdue_scan(db_session)

    queued = {
        call.kwargs["args"][0]
        for call in sent.call_args_list
        if call.args[0] == task_jobs.ANNOUNCE_ORG_TASK
    }
    assert count >= 1
    assert w.owner["organization"]["id"] in queued


def test_the_tasks_are_registered_and_scheduled_under_the_names_in_the_code():
    """A renamed task would silently stop running; pin the names the Beat schedule points at."""
    assert task_jobs.OVERDUE_SCAN_TASK in celery.tasks
    assert task_jobs.ANNOUNCE_ORG_TASK in celery.tasks
    assert celery.tasks[task_jobs.OVERDUE_SCAN_TASK].name == task_jobs.OVERDUE_SCAN_TASK
    assert celery.conf.beat_schedule["task-overdue-scan"]["task"] == task_jobs.OVERDUE_SCAN_TASK
    assert "app.modules.tasks.tasks" in celery.conf.include


@pytest.mark.asyncio
async def test_a_new_deadline_or_a_reassignment_earns_a_new_alert(client, monkeypatch, db_session):
    """Moving the deadline (still in the past) or reassigning re-arms the announcement."""
    w = await _world(client, monkeypatch, "d8")
    tid = (await _task(client, w.hr, w.dispatch, "Slippery", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)).json()["id"]
    await _run_scan_for(db_session, w)

    await client.patch(f"{TASKS}/{tid}", json={"due_at": ANOTHER_LONG_AGO}, headers=w.hr)
    after_edit = await _run_scan_for(db_session, w)
    nothing_changed = await _run_scan_for(db_session, w)

    assert (after_edit, nothing_changed) == (1, 0)
    assert len(await _overdue_titles(client, w.tunde.h)) == 2

    # A reassignment must set a future deadline, so it only re-arms (it isn't overdue yet).
    await client.post(
        f"{TASKS}/{tid}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": FAR_AHEAD},
        headers=w.hr,
    )
    assert await _run_scan_for(db_session, w) == 0
