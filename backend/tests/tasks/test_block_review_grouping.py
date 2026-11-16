"""One decision per task: blocks of the same task that are waiting are decided together (08_DECISIONS.md 2026-11-16).

Scenario: Chidi marks a task blocked, unblocks, and blocks again before anyone decided, so TWO blocks of the same task are
waiting. Two separate approvals would each add time and double the extension, so one decision covers them all and the
extra time is credited once.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.tasks import tasks as task_jobs
from tests.conftest import set_org_context
from tests.tasks.test_task_block_review import BLOCK, BLOCKS, _blocked_task, _titles, _world_with_a_boss
from tests.tasks.test_tasks_router import NOTIFICATIONS, TASKS, _clock_in


async def _two_waiting_blocks(client, w) -> tuple[str, str, str]:
    """A task Chidi blocked, unblocked and blocked again. Returns (task_id, first_block_id, second_block_id)."""
    task_id, first = await _blocked_task(client, w, "Stuck twice")
    await client.post(f"{TASKS}/{task_id}/unblock", headers=w.chidi.h)
    second = (await client.post(f"{TASKS}/{task_id}/block", json=BLOCK, headers=w.chidi.h)).json()["id"]
    return task_id, first, second


async def _task_now(client, w, task_id) -> dict:
    return (await client.get(f"{TASKS}/{task_id}", headers=w.hr)).json()


async def _blocks_of(client, w, task_id) -> dict[str, dict]:
    return {b["id"]: b for b in (await client.get(f"{TASKS}/{task_id}/blocks", headers=w.hr)).json()}


@pytest.mark.asyncio
async def test_one_approval_decides_both_and_credits_the_time_once(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "gr1")
    task_id, first, second = await _two_waiting_blocks(client, w)

    resp = await client.post(f"{BLOCKS}/{second}/approve", json={"extension_minutes": 60}, headers=w.dana.h)

    assert resp.status_code == 200
    blocks = await _blocks_of(client, w, task_id)
    assert blocks[first]["review_status"] == blocks[second]["review_status"] == "approved"
    assert blocks[second]["granted_seconds"] == 3600 and blocks[first]["granted_seconds"] is None  # the time is on one block
    assert all(b["unblocked_at"] is not None for b in blocks.values())  # the open one is ended too
    task = await _task_now(client, w, task_id)
    assert task["approved_blocked_seconds"] == 3600  # an hour once, not twice
    assert task["blocked_since"] is None
    assert (await client.get(BLOCKS, headers=w.dana.h)).json()["data"] == []  # nothing is left waiting


@pytest.mark.asyncio
async def test_deciding_the_older_block_covers_the_newer_one_too(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "gr2")
    task_id, first, second = await _two_waiting_blocks(client, w)

    await client.post(f"{BLOCKS}/{first}/approve", json={"extension_minutes": 30}, headers=w.dana.h)
    again = await client.post(f"{BLOCKS}/{second}/approve", json={"extension_minutes": 30}, headers=w.dana.h)

    assert again.status_code == 409 and again.json()["code"] == "TASK_BLOCK_ALREADY_REVIEWED"  # already decided with the first
    assert (await _task_now(client, w, task_id))["approved_blocked_seconds"] == 1800


@pytest.mark.asyncio
async def test_one_rejection_rejects_both(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "gr3")
    task_id, first, second = await _two_waiting_blocks(client, w)

    await client.post(f"{BLOCKS}/{second}/reject", headers=w.dana.h)

    blocks = await _blocks_of(client, w, task_id)
    assert blocks[first]["review_status"] == blocks[second]["review_status"] == "rejected"
    task = await _task_now(client, w, task_id)
    assert task["approved_blocked_seconds"] == 0 and task["blocked_since"] is None


@pytest.mark.asyncio
async def test_the_person_is_told_once_not_once_per_block(client, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "gr4")
    _, _, second = await _two_waiting_blocks(client, w)

    await client.post(f"{BLOCKS}/{second}/approve", json={"extension_minutes": 60}, headers=w.dana.h)

    assert await _titles(client, w.chidi.h, "Block approved") == ["Block approved: Stuck twice"]


@pytest.mark.asyncio
async def test_a_block_the_reviewer_may_not_decide_is_left_waiting(client, monkeypatch):
    """Dana reviews Chidi's blocks. After a reassignment Bola blocks the same task; Dana is not Bola's reviewer."""
    w = await _world_with_a_boss(client, monkeypatch, "gr5")
    task_id, chidis = await _blocked_task(client, w, "Passed on")
    await client.post(
        f"{TASKS}/{task_id}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": "2099-01-01T10:00:00+00:00"},
        headers=w.hr,
    )
    await _clock_in(client, w.bola)
    bolas = (await client.post(f"{TASKS}/{task_id}/block", json=BLOCK, headers=w.bola.h)).json()["id"]

    await client.post(f"{BLOCKS}/{chidis}/approve", json={"extension_minutes": 60}, headers=w.dana.h)

    blocks = await _blocks_of(client, w, task_id)
    assert blocks[chidis]["review_status"] == "approved"
    assert blocks[bolas]["review_status"] == "pending"  # Dana may not decide it, so it stays for its own reviewer


@pytest.mark.asyncio
async def test_two_waiting_blocks_are_chased_once_per_task(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "gr6")
    org_id = w.owner["organization"]["id"]
    task_id, first, second = await _two_waiting_blocks(client, w)
    now = datetime.now(UTC)
    await set_org_context(db_session, org_id)
    for block_id in (first, second):
        await db_session.execute(
            text("UPDATE task_blocks SET blocked_at = :at WHERE id = :id"), {"at": now - timedelta(hours=25), "id": block_id}
        )

    await task_jobs.run_announce_for_organization(db_session, uuid.UUID(org_id), now)

    assert await _titles(client, w.dana.h, "Block waiting for your review") == ["Block waiting for your review: Stuck twice"]
