"""Tests for what happens to an open block when its task ends or changes hands (M10 slice E, step 4).

Complete, cancel and reassign all end the block, so a block never outlives the
situation it describes.
"""
import pytest

from tests.tasks.test_task_block_review import (
    BLOCKS,
    _backdate_block,
    _blocked_task,
    _world_with_a_boss,
)
from tests.tasks.test_tasks_router import TASKS, _clock_in


async def _the_block(client, w, task_id) -> dict:
    """The task's most recent block, as the API shows it."""
    return (await client.get(f"{TASKS}/{task_id}/blocks", headers=w.hr)).json()[0]


@pytest.mark.asyncio
async def test_cancelling_a_blocked_task_ends_its_block(client, monkeypatch):
    """Tunde cancels the stuck task: the block is closed, still waiting for review, and the task is not blocked."""
    w = await _world_with_a_boss(client, monkeypatch, "es1")
    task_id, _ = await _blocked_task(client, w)

    resp = await client.post(f"{TASKS}/{task_id}/cancel", json={"reason": "No longer needed"}, headers=w.tunde.h)

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled" and resp.json()["blocked_since"] is None
    block = await _the_block(client, w, task_id)
    assert block["unblocked_at"] is not None and block["review_status"] == "pending"


@pytest.mark.asyncio
async def test_reassigning_a_blocked_task_ends_the_block_and_gives_the_new_person_a_clean_slate(
    client, monkeypatch, db_session
):
    """Even an approved day of blocked time stays with the old assignee: Bola starts at zero."""
    w = await _world_with_a_boss(client, monkeypatch, "es2")
    org_id = w.owner["organization"]["id"]
    task_id, block_id = await _blocked_task(client, w)
    await _backdate_block(db_session, org_id, block_id)
    await client.post(f"{BLOCKS}/{block_id}/approve", headers=w.dana.h)       # approved while still open

    resp = await client.post(
        f"{TASKS}/{task_id}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": "2099-01-01T10:00:00+00:00"},
        headers=w.hr,
    )

    assert resp.status_code == 200
    assert resp.json()["assigned_to_employee_id"] == w.bola.employee_id
    assert resp.json()["blocked_since"] is None and resp.json()["approved_blocked_seconds"] == 0
    block = await _the_block(client, w, task_id)
    assert block["unblocked_at"] is not None and block["review_status"] == "approved"      # the record stays


@pytest.mark.asyncio
async def test_completing_a_blocked_task_ends_its_block_and_credits_approved_time(client, monkeypatch, db_session):
    """Chidi finishes the task while a (backdated, approved) block is open: it closes and the day is credited."""
    w = await _world_with_a_boss(client, monkeypatch, "es3")
    org_id = w.owner["organization"]["id"]
    task_id, block_id = await _blocked_task(client, w)
    await _backdate_block(db_session, org_id, block_id)
    await client.post(f"{BLOCKS}/{block_id}/approve", headers=w.dana.h)

    resp = await client.post(f"{TASKS}/{task_id}/complete", headers=w.chidi.h)

    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    assert resp.json()["blocked_since"] is None
    assert 86400 <= resp.json()["approved_blocked_seconds"] < 86400 + 120
    assert (await _the_block(client, w, task_id))["unblocked_at"] is not None


@pytest.mark.asyncio
async def test_the_new_assignee_can_block_the_reassigned_task_afresh(client, monkeypatch):
    """After a reassignment the old block is gone, so Bola can start his own."""
    w = await _world_with_a_boss(client, monkeypatch, "es4")
    task_id, _ = await _blocked_task(client, w)
    await client.post(
        f"{TASKS}/{task_id}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": "2099-01-01T10:00:00+00:00"},
        headers=w.hr,
    )
    await _clock_in(client, w.bola)

    resp = await client.post(
        f"{TASKS}/{task_id}/block", json={"category": "other", "reason": "Waiting for parts"}, headers=w.bola.h
    )

    assert resp.status_code == 200 and resp.json()["blocked_by_user_id"] == w.bola.user_id
