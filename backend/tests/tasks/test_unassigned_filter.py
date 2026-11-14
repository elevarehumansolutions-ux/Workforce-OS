"""GET /tasks?unassigned=true: the "needs an owner" list (08_DECISIONS.md 2026-11-14, to-do 45).

Scenario: a workflow step in Dispatch has no default person, so its task has no assignee. Dispatch's head
(Tunde) and HR must see it in the list, an ordinary employee (Chidi) must not, and tasks that already
have an owner are left out.
"""
import pytest

from tests.tasks.test_tasks_router import DUE, TASKS, _task, _world
from tests.workflow.test_instance_start import _start, _template


async def _titles(client, headers, **params) -> list[str]:
    resp = await client.get(TASKS, params={"limit": 100, **params}, headers=headers)
    assert resp.status_code == 200, resp.text
    return [t["title"] for t in resp.json()["data"]]


@pytest.mark.asyncio
async def test_the_head_and_hr_see_unassigned_tasks_and_an_employee_does_not(client, monkeypatch):
    w = await _world(client, monkeypatch, "ua1")
    template = await _template(client, w, ("Dispatch the goods", w.dispatch, {}))
    await _start(client, w.hr, template["id"])
    expected = ["Dispatch the goods: Zenith Ltd"]

    assert await _titles(client, w.tunde.h, unassigned="true") == expected  # the head of Dispatch
    assert await _titles(client, w.hr, unassigned="true") == expected
    assert await _titles(client, w.chidi.h, unassigned="true") == []  # an employee of Dispatch


@pytest.mark.asyncio
async def test_a_task_with_an_owner_is_left_out_of_the_list(client, monkeypatch):
    w = await _world(client, monkeypatch, "ua2")
    await _task(client, w.hr, w.dispatch, title="Owned", assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)
    template = await _template(client, w, ("Needs someone", w.dispatch, {}))
    await _start(client, w.hr, template["id"])

    assert await _titles(client, w.hr, unassigned="true") == ["Needs someone: Zenith Ltd"]


@pytest.mark.asyncio
async def test_without_the_filter_the_list_is_unchanged(client, monkeypatch):
    w = await _world(client, monkeypatch, "ua3")
    await _task(client, w.hr, w.dispatch, title="Owned", assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)
    template = await _template(client, w, ("Needs someone", w.dispatch, {}))
    await _start(client, w.hr, template["id"])

    titles = await _titles(client, w.hr)

    assert sorted(titles) == ["Needs someone: Zenith Ltd", "Owned"]


@pytest.mark.asyncio
async def test_once_the_head_assigns_it_the_task_leaves_the_list(client, monkeypatch):
    w = await _world(client, monkeypatch, "ua4")
    template = await _template(client, w, ("Dispatch the goods", w.dispatch, {}))
    await _start(client, w.hr, template["id"])
    listed = (await client.get(TASKS, params={"unassigned": "true"}, headers=w.tunde.h)).json()["data"]

    resp = await client.post(
        f"{TASKS}/{listed[0]['id']}/reassign",
        json={"assigned_to_employee_id": w.chidi.employee_id, "due_at": DUE},
        headers=w.tunde.h,
    )

    assert resp.status_code == 200
    assert await _titles(client, w.tunde.h, unassigned="true") == []
