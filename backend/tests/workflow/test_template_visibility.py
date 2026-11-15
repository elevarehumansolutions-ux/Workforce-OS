"""Templates belong to their department (08_DECISIONS.md 2026-11-14, "Templates belong to their department").

Scenario: Dispatch owns "Client Onboarding". Dispatch's people (Chidi, Dana the manager, Tunde the head), HR and an
executive can see it and start cases from it. Sam, a Sales manager, cannot see it at all (it answers "not found"), and a
manager builds only for their own department. Sales still receives its own TASKS when it takes part in a step.
"""
import pytest

from tests.tasks.test_tasks_router import TASKS, _member, _world
from tests.workflow.test_instance_start import INSTANCES, _start
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create

STEPS = "/api/v1/workflow-steps"


async def _dispatch_template(client, w) -> dict:
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    assert (await _add(client, w.hr, template["id"], "Dispatch the goods", w.dispatch)).status_code == 200
    return template


@pytest.mark.asyncio
async def test_the_owning_department_hr_and_executives_can_read_a_template(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv1")
    template = await _dispatch_template(client, w)
    sales_position = (await client.get("/api/v1/positions", headers=w.hr)).json()["data"][0]["id"]
    executive = await _member(client, monkeypatch, w.hr, "tv1_eve@example.com", "business_executive", sales_position, "Eve")

    for who in (w.chidi.h, w.dana.h, w.tunde.h, w.hr, executive.h):
        assert (await client.get(f"{TEMPLATES}/{template['id']}", headers=who)).status_code == 200
        assert (await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=who)).status_code == 200


@pytest.mark.asyncio
async def test_another_department_cannot_see_the_template_or_its_steps(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv2")
    template = await _dispatch_template(client, w)

    read = await client.get(f"{TEMPLATES}/{template['id']}", headers=w.sam.h)
    steps = await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.sam.h)
    listed = await client.get(TEMPLATES, headers=w.sam.h)

    # The same "not found" as for a template that does not exist: its existence is not revealed.
    assert read.status_code == 404 and read.json()["code"] == "WORKFLOW_TEMPLATE_NOT_FOUND"
    assert steps.status_code == 404
    assert listed.status_code == 200 and listed.json()["data"] == []


@pytest.mark.asyncio
async def test_only_people_who_see_the_template_may_start_a_case_from_it(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv3")
    template = await _dispatch_template(client, w)

    by_outsider = await _start(client, w.sam.h, template["id"])
    by_member = await _start(client, w.chidi.h, template["id"])

    assert by_outsider.status_code == 404
    assert by_member.status_code == 200


@pytest.mark.asyncio
async def test_a_manager_builds_only_for_their_own_department(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv4")

    own = await client.post(TEMPLATES, json={"name": "Sales process", "department_id": w.sales}, headers=w.sam.h)
    elsewhere = await client.post(TEMPLATES, json={"name": "Dispatch process", "department_id": w.dispatch}, headers=w.sam.h)

    assert own.status_code == 200
    assert elsewhere.status_code == 403 and "own department" in elsewhere.json()["message"]
    # Sam builds steps in his own template, and Dana (Dispatch) cannot reach it.
    assert (await _add(client, w.sam.h, own.json()["id"], "Pitch", w.sales)).status_code == 200
    assert (await client.get(f"{TEMPLATES}/{own.json()['id']}", headers=w.dana.h)).status_code == 404
    assert (await _add(client, w.dana.h, own.json()["id"], "Sneaky", w.dispatch)).status_code == 404


@pytest.mark.asyncio
async def test_a_manager_cannot_hand_a_template_to_another_department(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv5")
    template = await _create(client, w.hr, "Onboarding", w.dispatch)

    resp = await client.patch(f"{TEMPLATES}/{template['id']}", json={"department_id": w.sales}, headers=w.dana.h)

    assert resp.status_code == 403
    assert (await client.get(f"{TEMPLATES}/{template['id']}", headers=w.hr)).json()["department_id"] == w.dispatch
    # HR may move it.
    assert (await client.patch(f"{TEMPLATES}/{template['id']}", json={"department_id": w.sales}, headers=w.hr)).status_code == 200


@pytest.mark.asyncio
async def test_hr_builds_for_any_department(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv6")

    resp = await client.post(TEMPLATES, json={"name": "Anything", "department_id": w.sales}, headers=w.hr)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_a_participating_department_gets_its_task_and_the_case_but_not_the_template(client, monkeypatch):
    """Sales takes part in a Dispatch step: Sam sees his task and the case, but still cannot open the template."""
    w = await _world(client, monkeypatch, "tv7")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _add(
        client, w.hr, template["id"], "Sign-off", w.dispatch,
        participants=[{"department_id": w.sales, "default_assignee_employee_id": w.sam.employee_id}],
    )
    case = (await _start(client, w.hr, template["id"])).json()

    sam_tasks = (await client.get(TASKS, params={"limit": 100}, headers=w.sam.h)).json()["data"]
    sam_case = await client.get(f"{INSTANCES}/{case['id']}", headers=w.sam.h)
    sam_template = await client.get(f"{TEMPLATES}/{template['id']}", headers=w.sam.h)

    assert [t["department_id"] for t in sam_tasks] == [w.sales]
    assert sam_case.status_code == 200
    assert sam_template.status_code == 404


@pytest.mark.asyncio
async def test_an_archived_template_is_still_seen_by_its_department_only(client, monkeypatch):
    w = await _world(client, monkeypatch, "tv8")
    template = await _dispatch_template(client, w)
    await client.post(f"{TEMPLATES}/{template['id']}/archive", headers=w.hr)

    by_member = await client.get(TEMPLATES, params={"include_archived": "true"}, headers=w.chidi.h)
    by_outsider = await client.get(TEMPLATES, params={"include_archived": "true"}, headers=w.sam.h)

    assert [t["name"] for t in by_member.json()["data"]] == ["Client Onboarding"]
    assert by_outsider.json()["data"] == []
