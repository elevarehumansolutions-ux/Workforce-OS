"""End-to-end tests of the chain (M11 slice D): finishing a task moves its case on.

Tasks of one case are all created inside one test transaction, where the
database clock stands still, so these tests match tasks by step, never by order.
"""
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.workflow.models import WorkflowInstance
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import AUDIT, DEPARTMENTS, NOTIFICATIONS, TASKS, _world
from tests.workflow.test_instance_start import INSTANCES, _start, _template
from tests.workflow.test_step_add import _add

LAGOS = ZoneInfo("Africa/Lagos")


async def _complete(client, headers, task_id: str):
    return await client.post(f"{TASKS}/{task_id}/complete", headers=headers)


async def _cancel(client, headers, task_id: str, reason: str = "Not needed"):
    return await client.post(f"{TASKS}/{task_id}/cancel", json={"reason": reason}, headers=headers)


async def _detail(client, w, case_id: str) -> dict:
    return (await client.get(f"{INSTANCES}/{case_id}", headers=w.hr)).json()


def _task_of(detail: dict, step_name: str) -> dict | None:
    """The task a case made for the named step, or None if that step has none yet."""
    steps = {s["id"]: s["name"] for s in detail["steps"]}
    for task in detail["tasks"]:
        if steps.get(task["workflow_step_id"]) == step_name:
            return task
    return None


async def _titles(client, headers) -> list[dict]:
    return (await client.get(NOTIFICATIONS, headers=headers)).json()


async def _three_step_case(client, monkeypatch, tag: str, starter: str = "chidi"):
    """Sales (24h, Dana) -> Dispatch (8h, no assignee; Tunde heads it) -> Legal (no turnaround)."""
    w = await _world(client, monkeypatch, tag)
    template = await _template(
        client, w,
        ("Sales hand-off", w.sales, {"default_assignee_employee_id": w.dana.employee_id, "default_turnaround_hours": 24}),
        ("Dispatch check", w.dispatch, {"default_turnaround_hours": 8}),
        ("Legal check", w.sales, {}),
    )
    case = (await _start(client, getattr(w, starter).h, template["id"], "Zenith Ltd")).json()
    return w, template, case


@pytest.mark.asyncio
async def test_finishing_each_task_creates_the_next_until_the_case_is_complete(client, monkeypatch):
    """Three steps: each completion creates exactly the next task; the last one completes the case."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch1")
    detail = await _detail(client, w, case["id"])
    assert len(detail["tasks"]) == 1 and _task_of(detail, "Dispatch check") is None

    first = _task_of(detail, "Sales hand-off")
    assert (await _complete(client, w.hr, first["id"])).status_code == 200
    detail = await _detail(client, w, case["id"])
    second = _task_of(detail, "Dispatch check")
    assert len(detail["tasks"]) == 2 and second["status"] == "open" and detail["status"] == "in_progress"
    assert second["title"] == "Dispatch check: Zenith Ltd" and second["department_id"] == w.dispatch
    assert _task_of(detail, "Legal check") is None

    assert (await _complete(client, w.hr, second["id"])).status_code == 200
    detail = await _detail(client, w, case["id"])
    third = _task_of(detail, "Legal check")
    assert len(detail["tasks"]) == 3 and third["due_at"] is None and detail["status"] == "in_progress"

    assert (await _complete(client, w.hr, third["id"])).status_code == 200
    detail = await _detail(client, w, case["id"])
    assert detail["status"] == "completed" and detail["completed_at"] is not None
    assert len(detail["tasks"]) == 3
    assert {t["status"] for t in detail["tasks"]} == {"completed"}
    audit = await client.get(AUDIT, params={"entity_type": "workflow_instance", "entity_id": case["id"]}, headers=w.hr)
    assert sorted(e["action"] for e in audit.json()["data"]) == ["complete", "start"]


@pytest.mark.asyncio
async def test_completing_a_task_twice_does_not_create_two_next_tasks(client, monkeypatch):
    """The second click is a 409 and the case still has just two tasks."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch2")
    first = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")

    once = await _complete(client, w.hr, first["id"])
    twice = await _complete(client, w.hr, first["id"])

    assert once.status_code == 200 and twice.status_code == 409 and twice.json()["code"] == "TASK_NOT_OPEN"
    assert len((await _detail(client, w, case["id"]))["tasks"]) == 2


@pytest.mark.asyncio
async def test_the_next_task_gets_its_own_deadline_assignee_and_notification(client, monkeypatch):
    """Dispatch (8h, no default assignee): a business-hours deadline from now, unassigned, Tunde (head) told."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch3")
    first = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")

    await _complete(client, w.hr, first["id"])

    second = _task_of(await _detail(client, w, case["id"]), "Dispatch check")
    due = datetime.fromisoformat(second["due_at"]).astimezone(LAGOS)
    assert due.weekday() < 5 and 9 <= due.hour <= 17
    assert 0 < (due.astimezone(UTC) - datetime.now(UTC)).total_seconds() < 5 * 86400
    assert second["assigned_to_employee_id"] is None
    assert "A task for Dispatch needs an owner" in [n["title"] for n in await _titles(client, w.tunde.h)]


@pytest.mark.asyncio
async def test_what_comes_next_is_read_from_the_template_as_it_is_now(client, monkeypatch):
    """A step added in the middle is passed through; deleting the last step makes the previous one final."""
    w, template, case = await _three_step_case(client, monkeypatch, "ch4")
    first = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")
    added = await _add(client, w.hr, template["id"], "Compliance", w.sales, step_order=2)
    assert added.status_code == 200

    await _complete(client, w.hr, first["id"])
    detail = await _detail(client, w, case["id"])
    compliance = _task_of(detail, "Compliance")
    assert compliance is not None and _task_of(detail, "Dispatch check") is None

    legal_step = next(s for s in detail["steps"] if s["name"] == "Legal check")
    assert (await client.delete(f"/api/v1/workflow-steps/{legal_step['id']}", headers=w.hr)).status_code == 200
    await _complete(client, w.hr, compliance["id"])
    dispatch = _task_of(await _detail(client, w, case["id"]), "Dispatch check")
    await _complete(client, w.hr, dispatch["id"])

    final = await _detail(client, w, case["id"])
    assert final["status"] == "completed" and len(final["tasks"]) == 3


@pytest.mark.asyncio
async def test_cancelling_a_step_by_hand_skips_it_tells_the_starter_and_is_audited(client, monkeypatch):
    """HR cancels the Dispatch task: Legal's task appears, Chidi (the starter) is told what and why."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch5")
    await _complete(client, w.hr, _task_of(await _detail(client, w, case["id"]), "Sales hand-off")["id"])
    dispatch = _task_of(await _detail(client, w, case["id"]), "Dispatch check")

    cancelled = await _cancel(client, w.hr, dispatch["id"], "Small client, no dispatch check needed")

    assert cancelled.status_code == 200
    detail = await _detail(client, w, case["id"])
    assert _task_of(detail, "Dispatch check")["status"] == "cancelled"
    assert _task_of(detail, "Legal check")["status"] == "open" and detail["status"] == "in_progress"
    skipped = [n for n in await _titles(client, w.chidi.h) if n["title"] == "A step was skipped on Zenith Ltd"]
    assert len(skipped) == 1
    assert '"Dispatch check" was skipped by' in skipped[0]["body"]
    assert "Small client, no dispatch check needed" in skipped[0]["body"]
    assert 'The case moved on to "Legal check"' in skipped[0]["body"]
    assert (skipped[0]["link_type"], skipped[0]["link_id"]) == ("workflow_instance", case["id"])
    audit = await client.get(AUDIT, params={"entity_type": "workflow_instance", "entity_id": case["id"]}, headers=w.hr)
    entry = next(e for e in audit.json()["data"] if e["action"] == "skip_step")
    assert entry["changes"]["new"]["step_name"] == "Dispatch check"
    assert entry["changes"]["new"]["reason"] == "Small client, no dispatch check needed"
    assert entry["changes"]["new"]["task_id"] == dispatch["id"]


@pytest.mark.asyncio
async def test_skipping_the_last_step_completes_the_case_and_says_so(client, monkeypatch):
    """No next step after the skipped one: the case completes and the message says it is now complete."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch6")
    await _complete(client, w.hr, _task_of(await _detail(client, w, case["id"]), "Sales hand-off")["id"])
    await _complete(client, w.hr, _task_of(await _detail(client, w, case["id"]), "Dispatch check")["id"])
    legal = _task_of(await _detail(client, w, case["id"]), "Legal check")

    await _cancel(client, w.hr, legal["id"], "Not needed for this client")

    detail = await _detail(client, w, case["id"])
    assert detail["status"] == "completed" and detail["completed_at"] is not None
    assert len(detail["tasks"]) == 3
    skipped = next(n for n in await _titles(client, w.chidi.h) if n["title"] == "A step was skipped on Zenith Ltd")
    assert "the case is now complete" in skipped["body"]


@pytest.mark.asyncio
async def test_the_starter_is_not_told_about_their_own_skip(client, monkeypatch):
    """Tunde starts the case and, as head of Dispatch, cancels the Dispatch task himself: no notification."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch7", starter="tunde")
    await _complete(client, w.hr, _task_of(await _detail(client, w, case["id"]), "Sales hand-off")["id"])
    dispatch = _task_of(await _detail(client, w, case["id"]), "Dispatch check")

    assert (await _cancel(client, w.tunde.h, dispatch["id"], "I will handle it elsewhere")).status_code == 200

    assert _task_of(await _detail(client, w, case["id"]), "Legal check") is not None
    assert "A step was skipped on Zenith Ltd" not in [n["title"] for n in await _titles(client, w.tunde.h)]


@pytest.mark.asyncio
async def test_a_cancelled_case_does_not_grow_a_new_task(client, monkeypatch, db_session):
    """The race rule: a task finishing after the case was cancelled creates nothing and leaves the case cancelled."""
    w, _, case = await _three_step_case(client, monkeypatch, "ch8")
    first = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")
    await set_org_context(db_session, w.owner["organization"]["id"])
    stored = await db_session.get(WorkflowInstance, uuid.UUID(case["id"]))
    stored.status, stored.cancel_reason = "cancelled", "Client withdrew"
    await db_session.flush()

    done = await _complete(client, w.hr, first["id"])

    assert done.status_code == 200
    detail = await _detail(client, w, case["id"])
    assert detail["status"] == "cancelled" and len(detail["tasks"]) == 1


@pytest.mark.asyncio
async def test_if_the_next_task_cannot_be_made_the_completion_fails_and_is_rolled_back(
    client, monkeypatch, db_session
):
    """Decision A: the next step's department is gone, so completing fails with a 404 and the task stays open."""
    w = await _world(client, monkeypatch, "ch9")
    legal_department = (await client.post(DEPARTMENTS, json={"name": "Legal"}, headers=w.hr)).json()["id"]
    template = await _template(
        client, w, ("Sales hand-off", w.sales, {}), ("Legal check", legal_department, {})
    )
    case = (await _start(client, w.chidi.h, template["id"])).json()
    first = _task_of(await _detail(client, w, case["id"]), "Sales hand-off")
    assert (await client.delete(f"{DEPARTMENTS}/{legal_department}", headers=w.hr)).status_code == 200

    # Production rolls the request back when it fails (get_db); the test client
    # shares one session, so the same rollback is done here with a savepoint.
    request_transaction = await db_session.begin_nested()
    failed = await _complete(client, w.hr, first["id"])
    await request_transaction.rollback()

    assert failed.status_code == 404 and failed.json()["code"] == "DEPARTMENT_NOT_FOUND"
    detail = await _detail(client, w, case["id"])
    assert _task_of(detail, "Sales hand-off")["status"] == "open"
    assert len(detail["tasks"]) == 1 and detail["status"] == "in_progress"


@pytest.mark.asyncio
async def test_ordinary_tasks_are_untouched_by_the_listeners(client, monkeypatch):
    """A standalone task completes and cancels exactly as before."""
    w = await _world(client, monkeypatch, "ch10")
    first = (await client.post(TASKS, json={"department_id": w.dispatch, "title": "Plain one"}, headers=w.hr)).json()
    second = (await client.post(TASKS, json={"department_id": w.dispatch, "title": "Plain two"}, headers=w.hr)).json()

    assert (await _complete(client, w.hr, first["id"])).status_code == 200
    assert (await _cancel(client, w.hr, second["id"])).status_code == 200
    assert (await client.get(INSTANCES, headers=w.hr)).json()["data"] == []
