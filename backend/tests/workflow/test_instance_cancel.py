"""Tests for POST /workflow-instances/{id}/cancel (M11 slice E)."""
import pytest

from tests.tasks.test_tasks_router import AUDIT, TASKS
from tests.workflow.test_chain import _complete, _detail, _task_of, _three_step_case, _titles
from tests.workflow.test_instance_start import INSTANCES


async def _cancel_case(client, headers, case_id: str, reason: str = "Client withdrew"):
    return await client.post(f"{INSTANCES}/{case_id}/cancel", json={"reason": reason}, headers=headers)


@pytest.mark.asyncio
async def test_the_starter_cancels_the_case_and_its_open_task_is_closed(client, monkeypatch):
    """Chidi cancels Zenith's case: the case is cancelled, Dana's open task is cancelled with the reason, and she is told."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic1")

    cancelled = await _cancel_case(client, w.chidi.h, case["id"], "  Client withdrew ")

    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled" and body["cancel_reason"] == "Client withdrew"
    assert body["completed_at"] is None and body["id"] == case["id"]
    detail = await _detail(client, w, case["id"])
    assert detail["status"] == "cancelled" and len(detail["tasks"]) == 1
    task = _task_of(detail, "Sales hand-off")
    assert task["status"] == "cancelled" and task["cancel_reason"] == "Client withdrew"
    told = [n for n in await _titles(client, w.dana.h) if n["title"] == "Task cancelled: Sales hand-off: Zenith Ltd"]
    assert len(told) == 1 and "Client withdrew" in told[0]["body"]
    assert "workflow was cancelled" in told[0]["body"]
    assert "A step was skipped on Zenith Ltd" not in [n["title"] for n in await _titles(client, w.chidi.h)]


@pytest.mark.asyncio
async def test_cancelling_mid_chain_closes_only_the_open_task_and_creates_nothing_more(client, monkeypatch):
    """Step 1 is done and step 2 is open: only step 2's task is cancelled; step 3 never appears; the audit entry says what happened."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic2")
    await _complete(client, w.hr, _task_of(await _detail(client, w, case["id"]), "Sales hand-off")["id"])

    cancelled = await _cancel_case(client, w.hr, case["id"], "Contract fell through")

    assert cancelled.status_code == 200
    detail = await _detail(client, w, case["id"])
    assert _task_of(detail, "Sales hand-off")["status"] == "completed"
    assert _task_of(detail, "Dispatch check")["status"] == "cancelled"
    assert _task_of(detail, "Legal check") is None and len(detail["tasks"]) == 2
    audit = await client.get(AUDIT, params={"entity_type": "workflow_instance", "entity_id": case["id"]}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "cancel")
    assert entry["actor_user_id"] == w.owner["user"]["id"]
    assert entry["changes"]["old"] == {"status": "in_progress", "cancel_reason": None}
    assert entry["changes"]["new"] == {"status": "cancelled", "cancel_reason": "Contract fell through", "tasks_cancelled": 1}


@pytest.mark.asyncio
async def test_hr_may_cancel_a_case_it_did_not_start(client, monkeypatch):
    """The HR administrator cancels Chidi's case; it then appears under the cancelled filter only."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic3")

    assert (await _cancel_case(client, w.hr, case["id"])).status_code == 200

    cancelled_list = await client.get(INSTANCES, params={"status": "cancelled"}, headers=w.hr)
    running_list = await client.get(INSTANCES, params={"status": "in_progress"}, headers=w.hr)
    assert [c["id"] for c in cancelled_list.json()["data"]] == [case["id"]]
    assert running_list.json()["data"] == []


@pytest.mark.asyncio
async def test_others_cannot_cancel_a_case_and_nothing_changes(client, monkeypatch):
    """The assignee and a department head can see the case but get a 403; an unrelated employee gets a 404."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic4")

    by_assignee = await _cancel_case(client, w.dana.h, case["id"])
    by_head = await _cancel_case(client, w.tunde.h, case["id"])  # heads Dispatch, which has a step
    by_stranger = await _cancel_case(client, w.bola.h, case["id"])

    assert by_assignee.status_code == 403 and by_head.status_code == 403
    assert "HR administrator or the person who started" in by_assignee.json()["message"]
    assert by_stranger.status_code == 404 and by_stranger.json()["code"] == "WORKFLOW_INSTANCE_NOT_FOUND"
    detail = await _detail(client, w, case["id"])
    assert detail["status"] == "in_progress" and _task_of(detail, "Sales hand-off")["status"] == "open"


@pytest.mark.asyncio
async def test_a_cancelled_case_cannot_be_cancelled_again(client, monkeypatch):
    """The second cancel is a 409 by name and the first reason stays."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic5")

    await _cancel_case(client, w.hr, case["id"])
    again = await _cancel_case(client, w.hr, case["id"], "Second time")

    assert again.status_code == 409 and again.json()["code"] == "WORKFLOW_INSTANCE_NOT_IN_PROGRESS"
    assert (await _detail(client, w, case["id"]))["cancel_reason"] == "Client withdrew"


@pytest.mark.asyncio
async def test_a_completed_case_cannot_be_cancelled(client, monkeypatch):
    """All three steps done, then a cancel: 409, and the case stays completed."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic8")
    for step_name in ("Sales hand-off", "Dispatch check", "Legal check"):
        await _complete(client, w.hr, _task_of(await _detail(client, w, case["id"]), step_name)["id"])

    refused = await _cancel_case(client, w.hr, case["id"])

    assert refused.status_code == 409 and refused.json()["code"] == "WORKFLOW_INSTANCE_NOT_IN_PROGRESS"
    assert (await _detail(client, w, case["id"]))["status"] == "completed"


@pytest.mark.asyncio
async def test_the_reason_is_required_and_the_case_must_exist(client, monkeypatch):
    """No, blank or too-long reason: 422. Unknown or malformed id: 404 / 422."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic9")
    url = f"{INSTANCES}/{case['id']}/cancel"

    missing = await client.post(url, json={}, headers=w.hr)
    blank = await _cancel_case(client, w.hr, case["id"], "   ")
    too_long = await _cancel_case(client, w.hr, case["id"], "x" * 501)
    unknown = await _cancel_case(client, w.hr, "00000000-0000-0000-0000-000000000000")
    malformed = await client.post(f"{INSTANCES}/not-an-id/cancel", json={"reason": "x"}, headers=w.hr)

    assert missing.status_code == 422 and blank.status_code == 422 and too_long.status_code == 422
    assert unknown.status_code == 404 and malformed.status_code == 422
    assert (await _detail(client, w, case["id"]))["status"] == "in_progress"


@pytest.mark.asyncio
async def test_a_blocked_task_is_closed_and_its_block_ends(client, monkeypatch):
    """Dana marked her task blocked; cancelling the case closes the task and ends the open block."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic11")
    task = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")
    await client.post("/api/v1/attendance/clock-in", headers=w.dana.h)
    block = {"category": "awaiting_other_department", "reason": "Waiting for Finance"}
    assert (await client.post(f"{TASKS}/{task['id']}/block", json=block, headers=w.dana.h)).status_code == 200
    assert (await client.get(f"{TASKS}/{task['id']}", headers=w.hr)).json()["blocked_since"] is not None

    cancelled = await _cancel_case(client, w.chidi.h, case["id"])

    assert cancelled.status_code == 200
    closed = (await client.get(f"{TASKS}/{task['id']}", headers=w.hr)).json()
    assert closed["status"] == "cancelled" and closed["blocked_since"] is None
    blocks = await client.get(f"{TASKS}/{task['id']}/blocks", headers=w.hr)
    assert [b["unblocked_at"] is not None for b in blocks.json()] == [True]


@pytest.mark.asyncio
async def test_a_task_cancelled_this_way_cannot_be_completed_afterwards(client, monkeypatch):
    """The closed task is final: completing it is a 409 and creates no next step."""
    w, _, case = await _three_step_case(client, monkeypatch, "ic10")
    task = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")
    await _cancel_case(client, w.hr, case["id"])

    late = await _complete(client, w.hr, task["id"])

    assert late.status_code == 409 and late.json()["code"] == "TASK_NOT_OPEN"
    assert len((await _detail(client, w, case["id"]))["tasks"]) == 1
    assert (await client.get(f"{TASKS}/{task['id']}", headers=w.hr)).json()["status"] == "cancelled"
