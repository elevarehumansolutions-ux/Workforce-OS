"""A block waiting for review too long is escalated (08_DECISIONS.md 2026-11-16).

While a block waits for a decision the task is not counted as overdue, so a reviewer who never decides would freeze the
clock. After 24 hours the people who may review it are reminded; after 48 hours HR is told too. Each happens once.
Scenario: Dana is Chidi's reporting manager, so she is his reviewer; Tunde heads Dispatch; Adaeze is HR.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.tasks import tasks as task_jobs
from app.modules.tasks.repository import TaskRepository
from tests.conftest import set_org_context
from tests.tasks.test_task_block_review import APPROVE, BLOCKS, EMPLOYEES, _blocked_task, _world_with_a_boss
from tests.tasks.test_tasks_router import NOTIFICATIONS

HOUR = timedelta(hours=1)


async def _wait(db_session, w, block_id: str, hours: float, now: datetime) -> None:
    """Make a block look like it was raised ``hours`` before ``now``."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(
        text("UPDATE task_blocks SET blocked_at = :at WHERE id = :id"), {"at": now - timedelta(hours=hours), "id": block_id}
    )


async def _scan_at(db_session, w, now: datetime) -> None:
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    await task_jobs.run_announce_for_organization(db_session, uuid.UUID(org_id), now)


async def _titles(client, headers, starts_with: str) -> list[str]:
    return [n["title"] for n in (await client.get(NOTIFICATIONS, headers=headers)).json() if n["title"].startswith(starts_with)]


@pytest.mark.asyncio
async def test_a_block_under_a_day_old_is_left_alone(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "re1")
    now = datetime.now(UTC)
    _, block_id = await _blocked_task(client, w, "Fresh")
    await _wait(db_session, w, block_id, 23, now)

    await _scan_at(db_session, w, now)

    assert await _titles(client, w.dana.h, "Block waiting") == []
    assert await _titles(client, w.hr, "A block has waited") == []


@pytest.mark.asyncio
async def test_after_a_day_the_reviewer_is_reminded_once_and_nobody_else(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "re2")
    now = datetime.now(UTC)
    _, block_id = await _blocked_task(client, w, "Get sign-off")
    await _wait(db_session, w, block_id, 25, now)

    await _scan_at(db_session, w, now)
    await _scan_at(db_session, w, now + 10 * timedelta(minutes=1))  # the scan runs every few minutes

    assert await _titles(client, w.dana.h, "Block waiting for your review") == ["Block waiting for your review: Get sign-off"]
    assert await _titles(client, w.tunde.h, "Block waiting") == []  # she has a boss on record, so only the boss is asked
    assert await _titles(client, w.hr, "A block has waited") == []  # not yet two days
    assert await _titles(client, w.chidi.h, "Block waiting") == []  # the blocker is never asked to review


@pytest.mark.asyncio
async def test_after_two_days_hr_is_told_once_and_the_reviewer_is_not_told_again(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "re3")
    now = datetime.now(UTC)
    _, block_id = await _blocked_task(client, w, "Get sign-off")
    await _wait(db_session, w, block_id, 25, now)
    await _scan_at(db_session, w, now)  # the reminder goes out

    await _wait(db_session, w, block_id, 49, now + 24 * HOUR)
    await _scan_at(db_session, w, now + 24 * HOUR)
    await _scan_at(db_session, w, now + 25 * HOUR)

    escalations = await _titles(client, w.hr, "A block has waited")
    assert escalations == ["A block has waited 2 days 1 hour for review: Get sign-off"]
    assert len(await _titles(client, w.dana.h, "Block waiting")) == 1  # still just the one reminder


@pytest.mark.asyncio
async def test_a_block_that_is_two_days_old_the_first_time_it_is_seen_gets_both(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "re4")
    now = datetime.now(UTC)
    _, block_id = await _blocked_task(client, w, "Forgotten")
    await _wait(db_session, w, block_id, 50, now)

    await _scan_at(db_session, w, now)

    assert len(await _titles(client, w.dana.h, "Block waiting for your review")) == 1
    assert len(await _titles(client, w.hr, "A block has waited")) == 1


@pytest.mark.asyncio
async def test_when_hr_is_already_the_reviewer_it_is_not_told_twice(client, db_session, monkeypatch):
    """No boss and no head to review (Sales has none): HR is the reviewer, so the reminder is HR's, with no duplicate."""
    w = await _world_with_a_boss(client, monkeypatch, "re5")
    await client.patch(f"{EMPLOYEES}/{w.sam.employee_id}", json={"manager_id": None}, headers=w.hr)
    sales_task = (await client.post(
        "/api/v1/tasks", json={"department_id": w.sales, "title": "Sales sign-off", "assigned_to_employee_id": w.sam.employee_id}, headers=w.hr
    )).json()["id"]
    from tests.tasks.test_tasks_router import _clock_in
    await _clock_in(client, w.sam)
    block = (await client.post(
        f"/api/v1/tasks/{sales_task}/block", json={"category": "other", "reason": "Waiting"}, headers=w.sam.h
    )).json()["id"]
    now = datetime.now(UTC)
    await _wait(db_session, w, block, 50, now)

    await _scan_at(db_session, w, now)

    assert await _titles(client, w.hr, "Block waiting for your review") == ["Block waiting for your review: Sales sign-off"]
    assert await _titles(client, w.hr, "A block has waited") == []  # already reminded as the reviewer


@pytest.mark.asyncio
async def test_a_block_that_has_been_decided_is_never_chased(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "re6")
    now = datetime.now(UTC)
    _, block_id = await _blocked_task(client, w, "Decided")
    await client.post(f"{BLOCKS}/{block_id}/approve", json=APPROVE, headers=w.dana.h)
    await _wait(db_session, w, block_id, 60, now)

    await _scan_at(db_session, w, now)

    assert await _titles(client, w.dana.h, "Block waiting") == []
    assert await _titles(client, w.hr, "A block has waited") == []


@pytest.mark.asyncio
async def test_the_scans_lookup_finds_an_organization_with_a_block_waiting_too_long(client, db_session, monkeypatch):
    w = await _world_with_a_boss(client, monkeypatch, "re7")
    org_id = uuid.UUID(w.owner["organization"]["id"])
    _, block_id = await _blocked_task(client, w, "Waiting")
    assert org_id not in await TaskRepository(db_session).list_organizations_needing_scan()

    await _wait(db_session, w, block_id, 30, datetime.now(UTC))

    assert org_id in await TaskRepository(db_session).list_organizations_needing_scan()
