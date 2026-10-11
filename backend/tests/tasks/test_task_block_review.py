"""Tests for reviewing blocks (M10 slice E, step 3).

Same company as the other task tests. Here Dana is Chidi's reporting manager
(his "boss"), Tunde heads Dispatch, Adaeze is HR; Bola and Sam are outsiders
to Chidi's blocks.
"""
import uuid

import pytest
from sqlalchemy import text

from tests.conftest import register_verified_and_login, set_org_context
from tests.tasks.test_tasks_router import NOTIFICATIONS, TASKS, _clock_in, _task, _world

BLOCKS = "/api/v1/task-blocks"
EMPLOYEES = "/api/v1/employees"
BLOCK = {"category": "awaiting_other_department", "reason": "Waiting for Finance to sign off"}


async def _world_with_a_boss(client, monkeypatch, tag):
    """The usual company, with Dana set as Chidi's reporting manager and Chidi clocked in."""
    w = await _world(client, monkeypatch, tag)
    await client.patch(f"{EMPLOYEES}/{w.chidi.employee_id}", json={"manager_id": w.dana.employee_id}, headers=w.hr)
    await _clock_in(client, w.chidi)
    return w


async def _blocked_task(client, w, title="Get sign-off") -> tuple[str, str]:
    """A task for Chidi that he has blocked. Returns (task_id, block_id)."""
    tid = (await _task(client, w.hr, w.dispatch, title, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    block = await client.post(f"{TASKS}/{tid}/block", json=BLOCK, headers=w.chidi.h)
    return tid, block.json()["id"]


async def _titles(client, headers, starts_with) -> list[str]:
    resp = await client.get(NOTIFICATIONS, headers=headers)
    return [n["title"] for n in resp.json() if n["title"].startswith(starts_with)]


@pytest.mark.asyncio
async def test_hr_the_head_and_the_boss_can_approve_but_the_blocker_and_strangers_cannot(client, monkeypatch):
    """Three reviewers each approve their own block; Chidi can't approve his own; outsiders get a 404."""
    w = await _world_with_a_boss(client, monkeypatch, "er1")
    _, by_hr = await _blocked_task(client, w, "One")
    _, by_head = await _blocked_task(client, w, "Two")
    _, by_boss = await _blocked_task(client, w, "Three")
    _, untouched = await _blocked_task(client, w, "Four")

    own = await client.post(f"{BLOCKS}/{untouched}/approve", headers=w.chidi.h)
    stranger = await client.post(f"{BLOCKS}/{untouched}/approve", headers=w.bola.h)
    other_manager = await client.post(f"{BLOCKS}/{untouched}/approve", headers=w.sam.h)
    unknown = await client.post(f"{BLOCKS}/{uuid.uuid4()}/approve", headers=w.hr)
    hr = await client.post(f"{BLOCKS}/{by_hr}/approve", headers=w.hr)
    head = await client.post(f"{BLOCKS}/{by_head}/approve", headers=w.tunde.h)
    boss = await client.post(f"{BLOCKS}/{by_boss}/approve", headers=w.dana.h)

    for refused in (own, stranger, other_manager, unknown):
        assert refused.status_code == 404 and refused.json()["code"] == "TASK_BLOCK_NOT_FOUND"
    assert hr.status_code == head.status_code == boss.status_code == 200
    assert hr.json()["review_status"] == "approved" and hr.json()["reviewed_by_user_id"] == w.owner["user"]["id"]
    assert boss.json()["reviewed_by_user_id"] == w.dana.user_id and boss.json()["reviewed_at"] is not None


@pytest.mark.asyncio
async def test_a_block_is_decided_once_and_the_blocker_is_told(client, monkeypatch):
    """Rejecting a reviewed block is a 409; the blocker is notified of the outcome."""
    w = await _world_with_a_boss(client, monkeypatch, "er2")
    _, approved = await _blocked_task(client, w, "Approved one")
    _, rejected = await _blocked_task(client, w, "Rejected one")

    first = await client.post(f"{BLOCKS}/{approved}/approve", headers=w.dana.h)
    again = await client.post(f"{BLOCKS}/{approved}/reject", headers=w.hr)
    same_again = await client.post(f"{BLOCKS}/{approved}/approve", headers=w.hr)
    no = await client.post(f"{BLOCKS}/{rejected}/reject", headers=w.tunde.h)

    assert first.status_code == 200 and no.json()["review_status"] == "rejected"
    for refused in (again, same_again):
        assert refused.status_code == 409 and refused.json()["code"] == "TASK_BLOCK_ALREADY_REVIEWED"
    told = set(await _titles(client, w.chidi.h, "Block "))
    assert told == {"Block approved: Approved one", "Block rejected: Rejected one"}


async def _backdate_block(db_session, org_id, block_id, days=1):
    """Make a block look like it started ``days`` ago (tests can't wait a day)."""
    await set_org_context(db_session, org_id)
    await db_session.execute(
        text("UPDATE task_blocks SET blocked_at = blocked_at - make_interval(days => :d) WHERE id = :id"),
        {"d": days, "id": block_id},
    )


@pytest.mark.asyncio
async def test_approving_a_finished_block_gives_the_time_back_and_rejecting_does_not(client, monkeypatch, db_session):
    """A day-long block: approved after unblocking -> about 86,400 seconds credited; rejected -> none."""
    w = await _world_with_a_boss(client, monkeypatch, "er3")
    org_id = w.owner["organization"]["id"]
    good_task, good_block = await _blocked_task(client, w, "Good block")
    bad_task, bad_block = await _blocked_task(client, w, "Bad block")
    await _backdate_block(db_session, org_id, good_block)
    await _backdate_block(db_session, org_id, bad_block)
    await client.post(f"{TASKS}/{good_task}/unblock", headers=w.chidi.h)
    await client.post(f"{TASKS}/{bad_task}/unblock", headers=w.chidi.h)

    await client.post(f"{BLOCKS}/{good_block}/approve", headers=w.dana.h)
    await client.post(f"{BLOCKS}/{bad_block}/reject", headers=w.dana.h)

    good = (await client.get(f"{TASKS}/{good_task}", headers=w.hr)).json()
    bad = (await client.get(f"{TASKS}/{bad_task}", headers=w.hr)).json()
    assert 86400 <= good["approved_blocked_seconds"] < 86400 + 120
    assert bad["approved_blocked_seconds"] == 0


@pytest.mark.asyncio
async def test_approving_a_block_that_is_still_open_credits_the_time_when_it_ends(client, monkeypatch, db_session):
    """Approve first, unblock later: nothing yet while blocked; the day is credited at unblock."""
    w = await _world_with_a_boss(client, monkeypatch, "er4")
    org_id = w.owner["organization"]["id"]
    tid, block_id = await _blocked_task(client, w)
    await _backdate_block(db_session, org_id, block_id)

    await client.post(f"{BLOCKS}/{block_id}/approve", headers=w.dana.h)
    while_blocked = (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()
    await client.post(f"{TASKS}/{tid}/unblock", headers=w.chidi.h)
    after = (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()

    assert while_blocked["approved_blocked_seconds"] == 0 and while_blocked["blocked_since"] is not None
    assert 86400 <= after["approved_blocked_seconds"] < 86400 + 120 and after["blocked_since"] is None


@pytest.mark.asyncio
async def test_the_review_list_shows_exactly_what_a_person_may_review(client, monkeypatch):
    """For every person, 'in my list' and 'allowed to approve' agree (the SQL and Python rules match)."""
    w = await _world_with_a_boss(client, monkeypatch, "er6")
    task_id, block_id = await _blocked_task(client, w, "Sign-off")
    people = {"hr": w.hr, "head": w.tunde.h, "boss": w.dana.h, "blocker": w.chidi.h, "colleague": w.bola.h, "other_manager": w.sam.h}

    in_list = {}
    for name, headers in people.items():
        listed = await client.get(BLOCKS, headers=headers)
        in_list[name] = block_id in [b["id"] for b in listed.json()["data"]]
    may_approve = {}
    for name, headers in people.items():
        attempt = await client.post(f"{BLOCKS}/{block_id}/approve", headers=headers)
        may_approve[name] = attempt.status_code != 404       # 200 the first time, then 409: both mean "allowed"

    assert in_list == may_approve
    assert in_list == {"hr": True, "head": True, "boss": True, "blocker": False, "colleague": False, "other_manager": False}
    row = (await client.get(BLOCKS, params={"review_status": "approved"}, headers=w.dana.h)).json()["data"][0]
    assert row["task_title"] == "Sign-off" and row["task_department_id"] == w.dispatch and row["task_id"] == task_id
    assert (await client.get(BLOCKS, headers=w.dana.h)).json()["data"] == []          # no longer pending


@pytest.mark.asyncio
async def test_the_review_list_is_paginated(client, monkeypatch):
    """Three pending blocks, two per page."""
    w = await _world_with_a_boss(client, monkeypatch, "er7")
    for title in ("A", "B", "C"):
        await _blocked_task(client, w, title)

    page1 = (await client.get(BLOCKS, params={"limit": 2}, headers=w.hr)).json()
    page2 = (await client.get(BLOCKS, params={"limit": 2, "page": 2}, headers=w.hr)).json()

    assert (len(page1["data"]), len(page2["data"]), page1["pagination"]["total"]) == (2, 1, 3)
    assert page1["pagination"]["has_next"] is True


@pytest.mark.asyncio
async def test_the_boss_is_told_first_then_the_head_then_hr(client, monkeypatch):
    """Chidi has a boss: only Dana hears. Without one, Tunde (head) does. In Sales (no head), HR does."""
    w = await _world_with_a_boss(client, monkeypatch, "er8")
    await _blocked_task(client, w, "With a boss")
    await client.patch(f"{EMPLOYEES}/{w.chidi.employee_id}", json={"manager_id": None}, headers=w.hr)
    await _blocked_task(client, w, "No boss")
    await _clock_in(client, w.sam)
    sales_task = (await _task(client, w.hr, w.sales, "Sales sign-off", assigned_to_employee_id=w.sam.employee_id)).json()["id"]
    await client.post(f"{TASKS}/{sales_task}/block", json=BLOCK, headers=w.sam.h)

    assert await _titles(client, w.dana.h, "Task blocked") == ["Task blocked: With a boss"]
    assert await _titles(client, w.tunde.h, "Task blocked") == ["Task blocked: No boss"]
    assert await _titles(client, w.hr, "Task blocked") == ["Task blocked: Sales sign-off"]
    assert await _titles(client, w.chidi.h, "Task blocked") == []        # the blocker is never told to review


@pytest.mark.asyncio
async def test_another_organization_cannot_review_a_block(client, monkeypatch):
    """Row-level security: a foreign HR administrator gets a 404."""
    w = await _world_with_a_boss(client, monkeypatch, "er5")
    _, block_id = await _blocked_task(client, w)
    other = await register_verified_and_login(client, email="tk_other_er5@example.com")

    foreign = await client.post(
        f"{BLOCKS}/{block_id}/approve", headers={"Authorization": f"Bearer {other['access_token']}"}
    )

    assert foreign.status_code == 404
