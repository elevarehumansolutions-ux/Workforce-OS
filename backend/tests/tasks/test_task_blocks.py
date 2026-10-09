"""Tests for blocking and unblocking tasks (M10 slice E).

Same company as the other task tests: Chidi and Bola work in Dispatch, Tunde
heads it, Dana is a Dispatch manager, Adaeze is HR.
"""
import pytest

from tests.conftest import register_verified_and_login
from tests.tasks.test_tasks_router import AUDIT, TASKS, _clock_in, _task, _world

BLOCK = {"category": "awaiting_other_department", "reason": "Waiting for Finance to sign off"}


async def _assigned_task(client, w, title="Get sign-off") -> str:
    """A task for Chidi, with Chidi clocked in so he can work on it."""
    await _clock_in(client, w.chidi)
    resp = await _task(client, w.hr, w.dispatch, title, assigned_to_employee_id=w.chidi.employee_id)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_the_assignee_marks_a_task_blocked(client, monkeypatch):
    """Chidi blocks it: a pending block is recorded and the task shows it is blocked."""
    w = await _world(client, monkeypatch, "eb1")
    tid = await _assigned_task(client, w)

    resp = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)

    assert resp.status_code == 200
    block = resp.json()
    assert block["task_id"] == tid and block["blocked_by_user_id"] == w.chidi.user_id
    assert block["category"] == "awaiting_other_department" and block["reason"] == BLOCK["reason"]
    assert block["review_status"] == "pending" and block["unblocked_at"] is None
    assert block["reviewed_by_user_id"] is None
    task = (await client.get(f"{TASKS}/{tid}", headers=w.chidi.h)).json()
    assert task["blocked_since"] == block["blocked_at"]
    assert task["approved_blocked_seconds"] == 0
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": tid}, headers=w.hr)
    assert "block" in {e["action"] for e in audit.json()["data"]}


@pytest.mark.asyncio
async def test_only_the_assignee_can_block_and_only_once_at_a_time(client, monkeypatch):
    """The head, a manager and HR can't block someone else's task; a second block is refused."""
    w = await _world(client, monkeypatch, "eb2")
    tid = await _assigned_task(client, w)

    by_head = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.tunde.h)
    by_manager = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.dana.h)
    by_hr = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.hr)
    first = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)
    second = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)

    for refused in (by_head, by_manager, by_hr):
        assert refused.status_code == 403 and refused.json()["code"] == "PERMISSION_DENIED"
    assert first.status_code == 200
    assert second.status_code == 409 and second.json()["code"] == "TASK_ALREADY_BLOCKED"


@pytest.mark.asyncio
async def test_bad_input_and_closed_tasks_are_refused(client, monkeypatch):
    """No reason, a blank reason, an unknown category, extra fields; finished or cancelled tasks can't be blocked."""
    w = await _world(client, monkeypatch, "eb3")
    tid = await _assigned_task(client, w)
    url = f"{TASKS}/{tid}/block"

    missing = await client.post(url, json={"category": "other"}, headers=w.chidi.h)
    blank = await client.post(url, json={"category": "other", "reason": "   "}, headers=w.chidi.h)
    bad_category = await client.post(url, json={"category": "boredom", "reason": "x"}, headers=w.chidi.h)
    too_long = await client.post(url, json={"category": "other", "reason": "x" * 501}, headers=w.chidi.h)
    extra = await client.post(url, json={**BLOCK, "review_status": "approved"}, headers=w.chidi.h)
    done = (await _task(client, w.hr, w.dispatch, "Done", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    await client.post(f"{TASKS}/{done}/complete", headers=w.hr)
    on_completed = await client.post(f"{TASKS}/{done}/block", json=BLOCK, headers=w.chidi.h)

    for refused in (missing, blank, bad_category, too_long, extra):
        assert refused.status_code == 422
    assert on_completed.status_code == 409 and on_completed.json()["code"] == "TASK_NOT_OPEN"
    assert (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()["blocked_since"] is None


@pytest.mark.asyncio
async def test_the_clock_in_gate_and_organization_walls_still_apply(client, monkeypatch):
    """An assignee who has not clocked in gets the gate's 409; another organization gets a 404."""
    w = await _world(client, monkeypatch, "eb4")
    tid = (await _task(client, w.hr, w.dispatch, "Gate", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    other = await register_verified_and_login(client, email="tk_other_eb4@example.com")
    other_h = {"Authorization": f"Bearer {other['access_token']}"}

    not_clocked_in = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)
    foreign = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=other_h)

    assert not_clocked_in.status_code == 409 and not_clocked_in.json()["code"] == "NOT_CLOCKED_IN"
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_unblocking_ends_the_block_and_the_task_can_be_blocked_again(client, monkeypatch):
    """Finance answers: Chidi unblocks, the block is closed, the task is free, and a later block is allowed."""
    w = await _world(client, monkeypatch, "eb5")
    tid = await _assigned_task(client, w)
    await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)

    resp = await client.post(f"{TASKS}/{tid}/unblock", headers=w.chidi.h)
    task = (await client.get(f"{TASKS}/{tid}", headers=w.chidi.h)).json()
    again = await client.post(f"{TASKS}/{tid}/block", json={**BLOCK, "category": "other"}, headers=w.chidi.h)
    history = await client.get(f"{TASKS}/{tid}/blocks", headers=w.chidi.h)

    assert resp.status_code == 200 and resp.json()["unblocked_at"] is not None
    assert resp.json()["review_status"] == "pending"
    assert task["blocked_since"] is None and task["approved_blocked_seconds"] == 0   # nothing approved yet
    assert again.status_code == 200
    # Newest first: the second (open) block, then the first (closed).
    assert [b["category"] for b in history.json()] == ["other", "awaiting_other_department"]
    assert history.json()[0]["unblocked_at"] is None and history.json()[1]["unblocked_at"] is not None


@pytest.mark.asyncio
async def test_who_can_unblock(client, monkeypatch):
    """The assignee, the head and HR can; a manager who is none of those cannot; an unblocked task can't be unblocked."""
    w = await _world(client, monkeypatch, "eb6")
    tid = await _assigned_task(client, w)

    nothing_to_unblock = await client.post(f"{TASKS}/{tid}/unblock", headers=w.chidi.h)
    await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)
    by_manager = await client.post(f"{TASKS}/{tid}/unblock", headers=w.dana.h)
    by_head = await client.post(f"{TASKS}/{tid}/unblock", headers=w.tunde.h)
    await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)
    by_hr = await client.post(f"{TASKS}/{tid}/unblock", headers=w.hr)
    await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)
    by_assignee = await client.post(f"{TASKS}/{tid}/unblock", headers=w.chidi.h)

    assert nothing_to_unblock.status_code == 409 and nothing_to_unblock.json()["code"] == "TASK_NOT_BLOCKED"
    assert by_manager.status_code == 403
    assert by_head.status_code == by_hr.status_code == by_assignee.status_code == 200
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": tid}, headers=w.hr)
    assert [e["action"] for e in audit.json()["data"]].count("unblock") == 3
