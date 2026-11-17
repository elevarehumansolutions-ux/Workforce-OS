"""The reviewer sets the extra time for an approved block (08_DECISIONS.md 2026-11-16, "The reviewer sets the time").

Scenario: Chidi marks a task blocked, optionally saying how much extra time he expects to need. His reviewer (Dana, his
reporting manager) approves and CHOOSES the time. It is credited at once, so it does not depend on how long Chidi stays
blocked, and approving ENDS the block. Rejecting also ends it, so a rejected block cannot leave the task "blocked, never
overdue".
"""
import pytest
from sqlalchemy import text

from app.modules.tasks.service import describe_duration
from tests.conftest import set_org_context
from tests.tasks.test_task_block_review import (
    BLOCK,
    BLOCKS,
    _backdate_block,
    _blocked_task,
    _titles,
    _world_with_a_boss,
)
from tests.tasks.past_deadlines import allow_past_deadlines  # noqa: F401 - used through usefixtures below
from tests.tasks.test_tasks_router import NOTIFICATIONS, TASKS, _task

# These tests need tasks that are already overdue (see tests/tasks/past_deadlines.py).
pytestmark = pytest.mark.usefixtures("allow_past_deadlines")

LONG_AGO = "2020-01-01T00:00:00+00:00"


async def _task_now(client, w, task_id) -> dict:
    return (await client.get(f"{TASKS}/{task_id}", headers=w.hr)).json()


@pytest.mark.asyncio
async def test_approving_credits_the_reviewers_time_at_once_and_ends_the_block(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex1")
    task_id, block_id = await _blocked_task(client, w)

    resp = await client.post(f"{BLOCKS}/{block_id}/approve", json={"extension_minutes": 120}, headers=w.dana.h)

    assert resp.status_code == 200
    body = resp.json()
    assert body["review_status"] == "approved" and body["granted_seconds"] == 7200
    assert body["unblocked_at"] is not None  # approving ENDS the block
    task = await _task_now(client, w, task_id)
    assert task["approved_blocked_seconds"] == 7200
    assert task["blocked_since"] is None  # the task is open again, no longer "Blocked"


@pytest.mark.asyncio
async def test_an_immediate_approval_gives_the_reviewers_time_not_the_minutes_that_passed(client, monkeypatch):
    """The worry: approving at once must not shrink the extension to a couple of minutes."""
    w = await _world_with_a_boss(client, monkeypatch, "ex2")
    task_id, block_id = await _blocked_task(client, w)

    await client.post(f"{BLOCKS}/{block_id}/approve", json={"extension_minutes": 1440}, headers=w.dana.h)

    assert (await _task_now(client, w, task_id))["approved_blocked_seconds"] == 86400  # a full day, exactly


@pytest.mark.asyncio
async def test_what_the_person_does_afterwards_cannot_change_the_time(client, monkeypatch, db_session):
    """The other worry: staying blocked longer must not earn more time. Approval ends the block, so there is nothing to stretch."""
    w = await _world_with_a_boss(client, monkeypatch, "ex3")
    org_id = w.owner["organization"]["id"]
    task_id, block_id = await _blocked_task(client, w)
    await _backdate_block(db_session, org_id, block_id, days=3)  # the person "stayed blocked" for three days

    await client.post(f"{BLOCKS}/{block_id}/approve", json={"extension_minutes": 60}, headers=w.dana.h)
    unblock = await client.post(f"{TASKS}/{task_id}/unblock", headers=w.chidi.h)

    assert unblock.status_code == 409  # already ended by the approval
    assert (await _task_now(client, w, task_id))["approved_blocked_seconds"] == 3600  # the reviewer's hour, not 3 days


@pytest.mark.asyncio
async def test_approving_a_block_the_person_already_ended_credits_the_reviewers_time(client, monkeypatch, db_session):
    w = await _world_with_a_boss(client, monkeypatch, "ex4")
    org_id = w.owner["organization"]["id"]
    task_id, block_id = await _blocked_task(client, w)
    await _backdate_block(db_session, org_id, block_id, days=1)
    await client.post(f"{TASKS}/{task_id}/unblock", headers=w.chidi.h)

    await client.post(f"{BLOCKS}/{block_id}/approve", json={"extension_minutes": 30}, headers=w.dana.h)

    assert (await _task_now(client, w, task_id))["approved_blocked_seconds"] == 1800  # not the day it lasted


@pytest.mark.asyncio
async def test_rejecting_ends_the_block_and_the_task_can_be_overdue_again(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex5")
    task_id = (await _task(client, w.hr, w.dispatch, "Late one", assigned_to_employee_id=w.chidi.employee_id, due_at=LONG_AGO)).json()["id"]
    block_id = (await client.post(f"{TASKS}/{task_id}/block", json=BLOCK, headers=w.chidi.h)).json()["id"]
    assert (await _task_now(client, w, task_id))["overdue"] is False  # blocked: never overdue

    resp = await client.post(f"{BLOCKS}/{block_id}/reject", headers=w.dana.h)

    assert resp.status_code == 200 and resp.json()["unblocked_at"] is not None and resp.json()["granted_seconds"] is None
    task = await _task_now(client, w, task_id)
    assert task["blocked_since"] is None and task["approved_blocked_seconds"] == 0
    assert task["overdue"] is True  # judged on its own deadline again


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"extension_minutes": 0}, {"extension_minutes": -5}, {"extension_minutes": 43201}, {"extension_minutes": "soon"}, {"extension_minutes": 5, "extra": 1}])
async def test_the_extension_must_be_a_whole_number_between_one_minute_and_thirty_days(client, monkeypatch, body):
    w = await _world_with_a_boss(client, monkeypatch, "ex6")
    task_id, block_id = await _blocked_task(client, w)

    resp = await client.post(f"{BLOCKS}/{block_id}/approve", json=body, headers=w.dana.h)

    assert resp.status_code == 422
    assert (await _task_now(client, w, task_id))["blocked_since"] is not None  # nothing was decided


@pytest.mark.asyncio
async def test_thirty_days_is_allowed(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex7")
    task_id, block_id = await _blocked_task(client, w)

    resp = await client.post(f"{BLOCKS}/{block_id}/approve", json={"extension_minutes": 43200}, headers=w.dana.h)

    assert resp.status_code == 200 and resp.json()["granted_seconds"] == 43200 * 60


@pytest.mark.asyncio
async def test_the_person_may_say_how_much_time_they_expect_to_need(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex8")
    tid = (await _task(client, w.hr, w.dispatch, "Waiting", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    asked = await client.post(f"{TASKS}/{tid}/block", json={**BLOCK, "estimated_minutes": 90}, headers=w.chidi.h)

    assert asked.status_code == 200 and asked.json()["estimated_seconds"] == 5400 and asked.json()["granted_seconds"] is None
    listed = (await client.get(BLOCKS, headers=w.dana.h)).json()["data"]
    assert listed[0]["estimated_seconds"] == 5400  # the reviewer sees what was asked
    assert listed[0]["task_approved_blocked_seconds"] == 0  # and what the task has been given so far


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, -1, 43201, "lots"])
async def test_a_bad_estimate_is_refused_and_the_task_is_not_blocked(client, monkeypatch, minutes):
    w = await _world_with_a_boss(client, monkeypatch, "ex9")
    tid = (await _task(client, w.hr, w.dispatch, "Waiting", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    resp = await client.post(f"{TASKS}/{tid}/block", json={**BLOCK, "estimated_minutes": minutes}, headers=w.chidi.h)

    assert resp.status_code == 422
    assert (await _task_now(client, w, tid))["blocked_since"] is None


@pytest.mark.asyncio
async def test_no_estimate_is_fine(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex10")
    _, block_id = await _blocked_task(client, w)

    block = (await client.get(BLOCKS, headers=w.dana.h)).json()["data"][0]

    assert block["id"] == block_id and block["estimated_seconds"] is None


@pytest.mark.asyncio
async def test_the_notices_say_who_decided_what_they_gave_and_the_deadline(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex11")
    approved_task = (await _task(client, w.hr, w.dispatch, "Approved one", assigned_to_employee_id=w.chidi.employee_id, due_at="2031-05-05T10:00:00+00:00")).json()["id"]
    approved = (await client.post(f"{TASKS}/{approved_task}/block", json=BLOCK, headers=w.chidi.h)).json()["id"]
    _, rejected = await _blocked_task(client, w, "Rejected one")

    await client.post(f"{BLOCKS}/{approved}/approve", json={"extension_minutes": 1560}, headers=w.dana.h)  # 1 day 2 hours
    await client.post(f"{BLOCKS}/{rejected}/reject", headers=w.dana.h)

    notices = {n["title"]: n["body"] for n in (await client.get(NOTIFICATIONS, headers=w.chidi.h)).json()}
    good = notices["Block approved: Approved one"]
    assert "Dana" in good and "1 day 2 hours" in good  # who, and how much
    assert "Deadline: Tue 06 May" in good and "Africa/Lagos" in good  # the new deadline (10:00 UTC + 26 h = 12:00 Lagos next day)
    assert "open again" in good
    bad = notices["Block rejected: Rejected one"]
    assert "Dana" in bad and "did not approve" in bad and "open again" in bad


@pytest.mark.asyncio
async def test_a_second_block_can_be_raised_after_an_approval_and_the_total_keeps_growing(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "ex12")
    task_id, first = await _blocked_task(client, w)
    await client.post(f"{BLOCKS}/{first}/approve", json={"extension_minutes": 60}, headers=w.dana.h)

    again = await client.post(f"{TASKS}/{task_id}/block", json=BLOCK, headers=w.chidi.h)
    await client.post(f"{BLOCKS}/{again.json()['id']}/approve", json={"extension_minutes": 30}, headers=w.dana.h)

    assert again.status_code == 200
    assert (await _task_now(client, w, task_id))["approved_blocked_seconds"] == 5400


@pytest.mark.asyncio
async def test_a_block_approved_under_the_old_rule_is_still_credited_by_how_long_it_lasted(client, monkeypatch, db_session):
    """Data from before this change: approved, still open, no reviewer-set time. Closing it credits its length, as it always did."""
    w = await _world_with_a_boss(client, monkeypatch, "ex13")
    org_id = w.owner["organization"]["id"]
    task_id, block_id = await _blocked_task(client, w)
    await _backdate_block(db_session, org_id, block_id, days=1)
    await set_org_context(db_session, org_id)
    await db_session.execute(
        text("UPDATE task_blocks SET review_status = 'approved', reviewed_by_user_id = :u, reviewed_at = now() WHERE id = :id"),
        {"u": w.dana.user_id, "id": block_id},
    )

    await client.post(f"{TASKS}/{task_id}/unblock", headers=w.chidi.h)

    assert 86400 <= (await _task_now(client, w, task_id))["approved_blocked_seconds"] < 86400 + 120


@pytest.mark.parametrize(
    "seconds, words",
    [(60, "1 minute"), (2700, "45 minutes"), (7200, "2 hours"), (93600, "1 day 2 hours"), (43200 * 60, "30 days"), (5, "1 minute")],
)
def test_durations_are_written_in_plain_words(seconds, words):
    assert describe_duration(seconds) == words
