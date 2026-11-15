"""GET /tasks/waiting-count: the red number on "Tasks" in the menu (to-do 52).

Scenario: Chidi has two tasks but has not clocked in; the number still says 2 (he cannot open them until he does).
Tunde heads Dispatch and sees the unassigned Dispatch task he must hand out; HR sees every department's.
"""
import pytest

from tests.tasks.test_tasks_router import DUE, TASKS, _task, _world
from tests.workflow.test_instance_start import _start, _template

COUNT = "/api/v1/tasks/waiting-count"


@pytest.mark.asyncio
async def test_open_tasks_assigned_to_me_are_counted_even_when_not_clocked_in(client, monkeypatch):
    w = await _world(client, monkeypatch, "wc1")
    for title in ("One", "Two"):
        await _task(client, w.hr, w.dispatch, title=title, assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)

    # The list itself is refused until he clocks in, but the count still works.
    assert (await client.get(TASKS, params={"assigned_to_employee_id": w.chidi.employee_id}, headers=w.chidi.h)).status_code == 409
    resp = await client.get(COUNT, headers=w.chidi.h)

    assert resp.status_code == 200
    assert resp.json() == {"assigned_to_me": 2, "to_hand_out": 0, "total": 2}


@pytest.mark.asyncio
async def test_a_completed_task_is_not_counted(client, monkeypatch):
    w = await _world(client, monkeypatch, "wc2")
    task = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)).json()
    await client.post(f"{TASKS}/{task['id']}/complete", headers=w.hr)

    assert (await client.get(COUNT, headers=w.chidi.h)).json()["total"] == 0


@pytest.mark.asyncio
async def test_a_head_and_hr_also_count_the_unassigned_tasks_they_hand_out(client, monkeypatch):
    w = await _world(client, monkeypatch, "wc3")
    template = await _template(client, w, ("Dispatch the goods", w.dispatch, {}))  # no named person
    await _start(client, w.hr, template["id"])

    assert (await client.get(COUNT, headers=w.tunde.h)).json() == {"assigned_to_me": 0, "to_hand_out": 1, "total": 1}
    assert (await client.get(COUNT, headers=w.hr)).json() == {"assigned_to_me": 0, "to_hand_out": 1, "total": 1}
    # An ordinary employee of Dispatch cannot hand it out, so it is not counted for them.
    assert (await client.get(COUNT, headers=w.chidi.h)).json() == {"assigned_to_me": 0, "to_hand_out": 0, "total": 0}


@pytest.mark.asyncio
async def test_a_head_only_counts_his_own_departments(client, monkeypatch):
    """The unassigned task is in Sales, which Tunde does not head; HR still counts it."""
    w = await _world(client, monkeypatch, "wc4")
    template = await _template(client, w, ("Close the deal", w.sales, {}))
    await _start(client, w.hr, template["id"])

    assert (await client.get(COUNT, headers=w.tunde.h)).json()["to_hand_out"] == 0
    assert (await client.get(COUNT, headers=w.hr)).json()["to_hand_out"] == 1


@pytest.mark.asyncio
async def test_the_count_needs_a_signed_in_person(client):
    assert (await client.get(COUNT)).status_code == 401
