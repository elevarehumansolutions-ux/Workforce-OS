"""A step that several departments do together (08_DECISIONS.md 2026-11-14, "Together steps").

Scenario: step 1 "Sign-off" is Dispatch's (its head, Tunde, receives it) and Sales is a participant with Sam named.
Starting the case creates ONE TASK PER DEPARTMENT, and each department's person is told and emailed. With the
rule "all" the case moves on to step 2 only when both tasks have ended; with "lead" only Dispatch's task counts and
Sales is a helper.
"""
import pytest

from app.modules.audit_and_notification.task_email import dispatch_task_email
from tests.tasks.test_tasks_router import KPIS, NOTIFICATIONS, TASKS, _world
from tests.workflow.test_instance_start import INSTANCES, _start, _tasks_of
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_list import _create

STEPS = "/api/v1/workflow-steps"


async def _together_template(client, w, rule: str = "all", sales_kpi: str | None = None) -> dict:
    """Step 1 Dispatch + Sales (Sam) together, then step 2 Dispatch (Chidi)."""
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    participant = {"department_id": w.sales, "default_assignee_employee_id": w.sam.employee_id}
    if sales_kpi:
        participant["kpi_id"] = sales_kpi
    added = await _add(
        client, w.hr, template["id"], "Sign-off", w.dispatch, participants=[participant], completion_rule=rule
    )
    assert added.status_code == 200, added.text
    after = await _add(
        client, w.hr, template["id"], "Deliver", w.dispatch, default_assignee_employee_id=w.chidi.employee_id
    )
    assert after.status_code == 200, after.text
    return template


async def _start_case(client, w, template) -> tuple[str, dict, dict]:
    """Start a case; return its id and the step-1 lead and participant tasks."""
    started = await _start(client, w.hr, template["id"])
    assert started.status_code == 200, started.text
    instance_id = started.json()["id"]
    tasks = await _tasks_of(client, w, instance_id)
    lead = next(t for t in tasks if t["workflow_task_role"] == "lead")
    helper = next(t for t in tasks if t["workflow_task_role"] == "participant")
    return instance_id, lead, helper


async def _complete(client, headers, task_id: str):
    return await client.post(f"{TASKS}/{task_id}/complete", headers=headers)


async def _task_titles_of_step_2(client, w, instance_id: str) -> list[str]:
    return [t["title"] for t in await _tasks_of(client, w, instance_id) if t["title"].startswith("Deliver")]


@pytest.mark.asyncio
async def test_starting_the_case_creates_one_task_per_department(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg1")
    template = await _together_template(client, w)

    instance_id, lead, helper = await _start_case(client, w, template)

    assert lead["department_id"] == w.dispatch and lead["assigned_to_employee_id"] is None  # goes to Dispatch's head
    assert helper["department_id"] == w.sales and helper["assigned_to_employee_id"] == w.sam.employee_id
    assert lead["workflow_step_id"] == helper["workflow_step_id"]
    assert lead["due_at"] == helper["due_at"]
    # Step 2 does not exist yet.
    assert await _task_titles_of_step_2(client, w, instance_id) == []


@pytest.mark.asyncio
async def test_each_department_is_told_and_emailed(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg2")
    sent = []
    monkeypatch.setattr(dispatch_task_email, "delay", lambda email, title, body, link: sent.append(email))
    template = await _together_template(client, w)

    await _start_case(client, w, template)

    # Sam (Sales' named person) and Tunde (Dispatch's head, nobody named) are both emailed.
    assert sorted(sent) == ["tk_sam_tg2@example.com", "tk_tunde_tg2@example.com"]
    sam_titles = [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.sam.h)).json()]
    tunde_titles = [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.tunde.h)).json()]
    assert "New task: Sign-off: Zenith Ltd" in sam_titles
    assert any("needs an owner" in t for t in tunde_titles)


@pytest.mark.asyncio
async def test_rule_all_waits_for_every_department_whichever_finishes_first(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg3")
    template = await _together_template(client, w, rule="all")
    instance_id, lead, helper = await _start_case(client, w, template)

    assert (await _complete(client, w.hr, helper["id"])).status_code == 200
    assert await _task_titles_of_step_2(client, w, instance_id) == []  # Dispatch has not finished

    assert (await _complete(client, w.hr, lead["id"])).status_code == 200
    assert await _task_titles_of_step_2(client, w, instance_id) == ["Deliver: Zenith Ltd"]


@pytest.mark.asyncio
async def test_rule_all_works_the_other_way_round_too(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg4")
    template = await _together_template(client, w, rule="all")
    instance_id, lead, helper = await _start_case(client, w, template)

    assert (await _complete(client, w.hr, lead["id"])).status_code == 200
    assert await _task_titles_of_step_2(client, w, instance_id) == []

    assert (await _complete(client, w.hr, helper["id"])).status_code == 200
    assert await _task_titles_of_step_2(client, w, instance_id) == ["Deliver: Zenith Ltd"]


@pytest.mark.asyncio
async def test_rule_all_a_cancelled_department_counts_as_ended(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg5")
    template = await _together_template(client, w, rule="all")
    instance_id, lead, helper = await _start_case(client, w, template)

    assert (await _complete(client, w.hr, lead["id"])).status_code == 200
    cancelled = await client.post(f"{TASKS}/{helper['id']}/cancel", json={"reason": "Not needed"}, headers=w.hr)

    assert cancelled.status_code == 200
    assert await _task_titles_of_step_2(client, w, instance_id) == ["Deliver: Zenith Ltd"]


@pytest.mark.asyncio
async def test_rule_lead_a_helper_finishing_does_not_move_the_case_on(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg6")
    template = await _together_template(client, w, rule="lead")
    instance_id, lead, helper = await _start_case(client, w, template)

    assert (await _complete(client, w.hr, helper["id"])).status_code == 200

    assert await _task_titles_of_step_2(client, w, instance_id) == []


@pytest.mark.asyncio
async def test_rule_lead_the_lead_finishing_moves_on_and_closes_open_helpers(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg7")
    template = await _together_template(client, w, rule="lead")
    instance_id, lead, helper = await _start_case(client, w, template)

    assert (await _complete(client, w.hr, lead["id"])).status_code == 200

    assert await _task_titles_of_step_2(client, w, instance_id) == ["Deliver: Zenith Ltd"]
    tasks = {t["id"]: t for t in await _tasks_of(client, w, instance_id)}
    assert tasks[helper["id"]]["status"] == "cancelled"
    assert tasks[helper["id"]]["cancel_reason"] == "The lead department finished this step."
    # The helper's person is told their help task was closed.
    assert "Task closed: Sign-off: Zenith Ltd" in [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.sam.h)).json()]


@pytest.mark.asyncio
async def test_rule_lead_a_helper_already_done_is_left_alone(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg8")
    template = await _together_template(client, w, rule="lead")
    instance_id, lead, helper = await _start_case(client, w, template)
    assert (await _complete(client, w.hr, helper["id"])).status_code == 200

    assert (await _complete(client, w.hr, lead["id"])).status_code == 200

    tasks = {t["id"]: t for t in await _tasks_of(client, w, instance_id)}
    assert tasks[helper["id"]]["status"] == "completed"
    assert await _task_titles_of_step_2(client, w, instance_id) == ["Deliver: Zenith Ltd"]


@pytest.mark.asyncio
async def test_cancelling_the_case_closes_every_departments_task(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg9")
    template = await _together_template(client, w)
    instance_id, lead, helper = await _start_case(client, w, template)

    resp = await client.post(f"{INSTANCES}/{instance_id}/cancel", json={"reason": "Client withdrew"}, headers=w.hr)

    assert resp.status_code == 200
    statuses = {t["id"]: t["status"] for t in await _tasks_of(client, w, instance_id)}
    assert statuses == {lead["id"]: "cancelled", helper["id"]: "cancelled"}


@pytest.mark.asyncio
async def test_the_case_detail_shows_the_participants_and_each_tasks_role(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg10")
    template = await _together_template(client, w, rule="lead")
    instance_id, lead, helper = await _start_case(client, w, template)

    detail = (await client.get(f"{INSTANCES}/{instance_id}", headers=w.hr)).json()

    step_1 = detail["steps"][0]
    assert step_1["completion_rule"] == "lead"
    assert [p["department_id"] for p in step_1["participants"]] == [w.sales]
    assert {t["workflow_task_role"] for t in detail["tasks"]} == {"lead", "participant"}
    assert detail["steps"][1]["participants"] == []


@pytest.mark.asyncio
async def test_an_ordinary_step_is_unchanged(client, monkeypatch):
    """No participants: one task, no role, the case moves on as it always did."""
    w = await _world(client, monkeypatch, "tg11")
    template = await _create(client, w.hr, "Simple", w.dispatch)
    await _add(client, w.hr, template["id"], "One", w.dispatch, default_assignee_employee_id=w.chidi.employee_id)
    await _add(client, w.hr, template["id"], "Two", w.dispatch, default_assignee_employee_id=w.chidi.employee_id)
    started = await _start(client, w.hr, template["id"])
    instance_id = started.json()["id"]
    tasks = await _tasks_of(client, w, instance_id)
    assert [t["workflow_task_role"] for t in tasks] == [None]

    assert (await _complete(client, w.hr, tasks[0]["id"])).status_code == 200

    assert sorted(t["title"] for t in await _tasks_of(client, w, instance_id)) == ["One: Zenith Ltd", "Two: Zenith Ltd"]


# ---- building and editing the extra departments


@pytest.mark.asyncio
async def test_a_step_returns_its_participants_and_rule(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg12")
    template = await _create(client, w.hr, "T", w.dispatch)

    added = await _add(
        client, w.hr, template["id"], "Sign-off", w.dispatch,
        participants=[{"department_id": w.sales}], completion_rule="lead",
    )

    body = added.json()
    assert body["completion_rule"] == "lead"
    assert [(p["department_id"], p["default_assignee_employee_id"], p["kpi_id"]) for p in body["participants"]] == [
        (w.sales, None, None)
    ]
    listed = (await client.get(f"/api/v1/workflow-templates/{template['id']}/steps", headers=w.hr)).json()
    assert listed[0]["participants"][0]["department_id"] == w.sales


@pytest.mark.asyncio
async def test_a_participants_kpi_must_belong_to_its_own_department(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg13")
    dispatch_kpi = (await client.post(KPIS, json={"department_id": w.dispatch, "name": "On time", "weight": 100}, headers=w.hr)).json()["id"]
    sales_kpi = (await client.post(KPIS, json={"department_id": w.sales, "name": "Deals", "weight": 100}, headers=w.hr)).json()["id"]
    template = await _create(client, w.hr, "T", w.dispatch)

    wrong = await _add(
        client, w.hr, template["id"], "Sign-off", w.dispatch,
        participants=[{"department_id": w.sales, "kpi_id": dispatch_kpi}],
    )
    right = await _add(
        client, w.hr, template["id"], "Sign-off", w.dispatch,
        participants=[{"department_id": w.sales, "kpi_id": sales_kpi}],
    )

    assert wrong.status_code == 422 and "another department" in wrong.json()["message"]
    assert right.status_code == 200 and right.json()["participants"][0]["kpi_id"] == sales_kpi


@pytest.mark.asyncio
async def test_the_participants_task_carries_its_own_kpi(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg14")
    sales_kpi = (await client.post(KPIS, json={"department_id": w.sales, "name": "Deals", "weight": 100}, headers=w.hr)).json()["id"]
    template = await _together_template(client, w, sales_kpi=sales_kpi)

    _, lead, helper = await _start_case(client, w, template)

    assert helper["kpi_id"] == sales_kpi and lead["kpi_id"] is None


@pytest.mark.asyncio
async def test_unknown_department_duplicates_and_too_many_are_refused(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg15")
    template = await _create(client, w.hr, "T", w.dispatch)

    unknown = await _add(
        client, w.hr, template["id"], "S", w.dispatch,
        participants=[{"department_id": "00000000-0000-4000-8000-000000000000"}],
    )
    twice = await _add(
        client, w.hr, template["id"], "S", w.dispatch,
        participants=[{"department_id": w.sales}, {"department_id": w.sales}],
    )
    same_as_own = await _add(
        client, w.hr, template["id"], "S", w.dispatch, participants=[{"department_id": w.dispatch}]
    )
    six = await _add(
        client, w.hr, template["id"], "S", w.dispatch, participants=[{"department_id": w.sales}] * 6
    )

    assert unknown.status_code == 404
    assert twice.status_code == 422 and "listed twice" in twice.json()["message"]
    assert same_as_own.status_code == 422  # the step's own department with nobody named repeats the step itself
    assert six.status_code == 422
    assert (await client.get(f"/api/v1/workflow-templates/{template['id']}/steps", headers=w.hr)).json() == []


@pytest.mark.asyncio
async def test_editing_replaces_the_whole_list_and_an_empty_list_removes_them(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg16")
    template = await _create(client, w.hr, "T", w.dispatch)
    step = (await _add(client, w.hr, template["id"], "S", w.dispatch, participants=[{"department_id": w.sales}])).json()

    changed = await client.patch(
        f"{STEPS}/{step['id']}",
        json={"participants": [{"department_id": w.sales, "default_assignee_employee_id": w.sam.employee_id}], "completion_rule": "lead"},
        headers=w.hr,
    )
    cleared = await client.patch(f"{STEPS}/{step['id']}", json={"participants": []}, headers=w.hr)
    untouched = await client.patch(f"{STEPS}/{step['id']}", json={"name": "Renamed"}, headers=w.hr)

    assert changed.status_code == 200
    assert [p["default_assignee_employee_id"] for p in changed.json()["participants"]] == [w.sam.employee_id]
    assert changed.json()["completion_rule"] == "lead"
    assert cleared.json()["participants"] == []
    assert untouched.status_code == 200 and untouched.json()["participants"] == []


@pytest.mark.asyncio
async def test_a_bad_rule_is_refused(client, monkeypatch):
    w = await _world(client, monkeypatch, "tg17")
    template = await _create(client, w.hr, "T", w.dispatch)

    resp = await _add(client, w.hr, template["id"], "S", w.dispatch, completion_rule="whoever")

    assert resp.status_code == 422
