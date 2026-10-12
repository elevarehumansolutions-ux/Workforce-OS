"""Tests for GET /workflow-instances and /workflow-instances/{id} (M11 slice C): who sees which case."""
import uuid
from datetime import UTC, datetime

import pytest

from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import POSITIONS, _member, _world
from tests.workflow.test_instance_start import INSTANCES, _start, _tasks_of, _template
from tests.workflow.test_workflow_tables import _instance


def _ids(response) -> list[str]:
    return [case["id"] for case in response.json()["data"]]


async def _onboarding_world(client, monkeypatch, tag: str):
    """A company with a two-step template: Sales (Sam's default) then Dispatch (Tunde heads it)."""
    w = await _world(client, monkeypatch, tag)
    template = await _template(
        client, w,
        ("Sales hand-off", w.sales, {"default_assignee_employee_id": w.sam.employee_id}),
        ("Dispatch check", w.dispatch, {}),
    )
    return w, template


@pytest.mark.asyncio
async def test_who_sees_a_case_and_who_does_not(client, monkeypatch):
    """HR, the starter, the first-step assignee and the head of a department with a step see it; others get a 404."""
    w, template = await _onboarding_world(client, monkeypatch, "ir1")
    case = (await _start(client, w.chidi.h, template["id"])).json()
    url = f"{INSTANCES}/{case['id']}"

    sees = {
        "hr": w.hr, "starter chidi": w.chidi.h, "assignee sam": w.sam.h,
        # Tunde heads Dispatch, which has step 2 although its task does not exist yet.
        "head tunde": w.tunde.h,
    }
    hidden = {
        # Bola is an unrelated employee; Dana is a manager of Dispatch but not its head.
        "bola": w.bola.h, "manager dana": w.dana.h,
    }
    for name, headers in sees.items():
        assert (await client.get(url, headers=headers)).status_code == 200, name
        assert _ids(await client.get(INSTANCES, headers=headers)) == [case["id"]], name
    for name, headers in hidden.items():
        refused = await client.get(url, headers=headers)
        assert refused.status_code == 404 and refused.json()["code"] == "WORKFLOW_INSTANCE_NOT_FOUND", name
        assert _ids(await client.get(INSTANCES, headers=headers)) == [], name


@pytest.mark.asyncio
async def test_a_business_executive_sees_every_case(client, monkeypatch):
    """The organization-wide roles need no connection to the case."""
    w, template = await _onboarding_world(client, monkeypatch, "ir2")
    position = (await client.post(POSITIONS, json={"department_id": w.sales, "title": "Executive"}, headers=w.hr)).json()
    executive = await _member(client, monkeypatch, w.hr, "ir2_exec@example.com", "business_executive", position["id"], "Exec")
    case = (await _start(client, w.chidi.h, template["id"])).json()

    seen = await client.get(f"{INSTANCES}/{case['id']}", headers=executive.h)

    assert seen.status_code == 200
    assert _ids(await client.get(INSTANCES, headers=executive.h)) == [case["id"]]


@pytest.mark.asyncio
async def test_someone_who_finished_their_part_still_sees_the_case(client, monkeypatch):
    """A person with a task in the case, even a completed one, keeps seeing it (clock-in does not matter for cases)."""
    w, template = await _onboarding_world(client, monkeypatch, "ir3")
    case = (await _start(client, w.chidi.h, template["id"])).json()
    task = (await _tasks_of(client, w, case["id"]))[0]
    await client.post("/api/v1/attendance/clock-in", headers=w.sam.h)
    assert (await client.post(f"/api/v1/tasks/{task['id']}/complete", headers=w.sam.h)).status_code == 200

    seen = await client.get(f"{INSTANCES}/{case['id']}", headers=w.sam.h)

    assert seen.status_code == 200
    assert [t["status"] for t in seen.json()["tasks"]] == ["completed"]


@pytest.mark.asyncio
async def test_the_detail_shows_the_current_steps_and_the_tasks_so_far(client, monkeypatch):
    """Two steps, one task so far; the task points at its step."""
    w, template = await _onboarding_world(client, monkeypatch, "ir4")
    case = (await _start(client, w.chidi.h, template["id"], "Zenith Ltd")).json()

    detail = (await client.get(f"{INSTANCES}/{case['id']}", headers=w.hr)).json()

    assert detail["subject"] == "Zenith Ltd" and detail["status"] == "in_progress"
    assert [(s["step_order"], s["name"]) for s in detail["steps"]] == [(1, "Sales hand-off"), (2, "Dispatch check")]
    assert len(detail["tasks"]) == 1
    task = detail["tasks"][0]
    assert task["workflow_step_id"] == detail["steps"][0]["id"]
    assert task["title"] == "Sales hand-off: Zenith Ltd" and task["status"] == "open"
    assert task["assigned_to_employee_id"] == w.sam.employee_id
    assert set(task) == {
        "id", "workflow_step_id", "department_id", "assigned_to_employee_id", "title", "status",
        "due_at", "completed_at", "cancel_reason", "created_at",
    }


@pytest.mark.asyncio
async def test_the_list_filters_by_status_and_template_and_is_paginated_newest_first(
    client, monkeypatch, db_session
):
    """Two templates, three cases (one finished): each filter narrows the list; pages hold what they should."""
    w, onboarding = await _onboarding_world(client, monkeypatch, "ir5")
    refunds = await _template(client, w, ("Refund check", w.sales, {}))
    first = (await _start(client, w.hr, onboarding["id"], "First")).json()
    second = (await _start(client, w.hr, refunds["id"], "Second")).json()
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    finished = _instance(
        org_id, uuid.UUID(onboarding["id"]), subject="Third", status="completed", completed_at=datetime.now(UTC)
    )
    db_session.add(finished)
    await db_session.flush()

    everything = await client.get(INSTANCES, headers=w.hr)
    running = await client.get(INSTANCES, params={"status": "in_progress"}, headers=w.hr)
    completed = await client.get(INSTANCES, params={"status": "completed"}, headers=w.hr)
    of_refunds = await client.get(INSTANCES, params={"template_id": refunds["id"]}, headers=w.hr)
    page_one = await client.get(INSTANCES, params={"limit": 2}, headers=w.hr)
    page_two = await client.get(INSTANCES, params={"limit": 2, "page": 2}, headers=w.hr)
    bad_status = await client.get(INSTANCES, params={"status": "paused"}, headers=w.hr)

    assert set(_ids(everything)) == {first["id"], second["id"], str(finished.id)}
    assert set(_ids(running)) == {first["id"], second["id"]} and _ids(completed) == [str(finished.id)]
    assert _ids(of_refunds) == [second["id"]]
    assert everything.json()["pagination"]["total"] == 3
    assert len(_ids(page_one)) == 2 and len(_ids(page_two)) == 1
    assert _ids(page_one) + _ids(page_two) == _ids(everything)
    assert bad_status.status_code == 422


@pytest.mark.asyncio
async def test_another_company_never_sees_the_case(client, monkeypatch):
    """Row-level security: another company's HR gets an empty list and a 404."""
    w, template = await _onboarding_world(client, monkeypatch, "ir6")
    other = await _world(client, monkeypatch, "ir7")
    case = (await _start(client, w.chidi.h, template["id"])).json()
    unknown = f"{INSTANCES}/00000000-0000-0000-0000-000000000000"

    assert _ids(await client.get(INSTANCES, headers=other.hr)) == []
    assert (await client.get(f"{INSTANCES}/{case['id']}", headers=other.hr)).status_code == 404
    assert (await client.get(unknown, headers=w.hr)).status_code == 404
    assert (await client.get(f"{INSTANCES}/not-an-id", headers=w.hr)).status_code == 422
    assert case["id"] not in _ids(await client.get(INSTANCES, headers=other.hr))
