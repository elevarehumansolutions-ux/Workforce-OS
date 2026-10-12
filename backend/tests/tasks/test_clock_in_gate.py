"""Tests for the clock-in gate (M10 slice C).

"Employee clocks in -> task list becomes visible (never shown before clock-in)"
(01_REQUIREMENTS.md). Only the *assignee* view is gated: what someone sees as
a creator, department head, manager, HR or executive is not.
"""
import pytest

from tests.tasks.test_tasks_router import TASKS, _clock_in, _ids, _task, _world

ATTENDANCE = "/api/v1/attendance"


@pytest.mark.asyncio
async def test_an_assignee_sees_and_completes_their_tasks_only_while_clocked_in(client, monkeypatch):
    """Chidi at 8:55 sees nothing and gets a clear 409; once clocked in it all works; clocked out, it's hidden again."""
    w = await _world(client, monkeypatch, "c1")
    tid = (await _task(client, w.hr, w.dispatch, "Morning run", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    before_list = await client.get(TASKS, headers=w.chidi.h)
    before_detail = await client.get(f"{TASKS}/{tid}", headers=w.chidi.h)
    before_complete = await client.post(f"{TASKS}/{tid}/complete", headers=w.chidi.h)
    await _clock_in(client, w.chidi)
    during_list = await client.get(TASKS, headers=w.chidi.h)
    during_detail = await client.get(f"{TASKS}/{tid}", headers=w.chidi.h)
    await client.post(f"{ATTENDANCE}/clock-out", headers=w.chidi.h)
    after_detail = await client.get(f"{TASKS}/{tid}", headers=w.chidi.h)

    assert before_list.status_code == 200 and before_list.json()["data"] == []
    for refused in (before_detail, before_complete, after_detail):
        assert refused.status_code == 409 and refused.json()["code"] == "NOT_CLOCKED_IN"
        assert "Clock in" in refused.json()["message"]
    assert _ids(during_list) == [tid] and during_detail.status_code == 200
    # Nothing was completed while he was locked out.
    assert (await client.get(f"{TASKS}/{tid}", headers=w.hr)).json()["status"] == "open"


@pytest.mark.asyncio
async def test_asking_for_my_own_tasks_before_clocking_in_says_so_instead_of_an_empty_list(client, monkeypatch):
    """The "My tasks" screen gets a 409 it can act on; everyone else's list requests are unaffected."""
    w = await _world(client, monkeypatch, "c6")
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    mine = await client.get(TASKS, params={"assigned_to_employee_id": w.chidi.employee_id}, headers=w.chidi.h)
    someone_elses = await client.get(TASKS, params={"assigned_to_employee_id": w.chidi.employee_id}, headers=w.tunde.h)
    unfiltered = await client.get(TASKS, headers=w.chidi.h)
    await _clock_in(client, w.chidi)
    mine_clocked_in = await client.get(TASKS, params={"assigned_to_employee_id": w.chidi.employee_id}, headers=w.chidi.h)

    assert mine.status_code == 409 and mine.json()["code"] == "NOT_CLOCKED_IN"
    assert "Clock in" in mine.json()["message"]
    assert _ids(someone_elses) == [tid]                  # the head asking about Chidi's tasks: fine
    assert unfiltered.status_code == 200 and unfiltered.json()["data"] == []
    assert _ids(mine_clocked_in) == [tid]


@pytest.mark.asyncio
async def test_the_head_and_hr_do_not_need_to_be_clocked_in_to_manage_the_department(client, monkeypatch):
    """Tunde (not clocked in) still sees Dispatch's tasks and can complete one; so can HR."""
    w = await _world(client, monkeypatch, "c2")
    tid = (await _task(client, w.hr, w.dispatch, "Chidi's", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    other = (await _task(client, w.hr, w.dispatch, "Bola's", assigned_to_employee_id=w.bola.employee_id)).json()["id"]

    head_list = await client.get(TASKS, headers=w.tunde.h)
    head_complete = await client.post(f"{TASKS}/{tid}/complete", headers=w.tunde.h)
    manager_list = await client.get(TASKS, headers=w.dana.h)      # manager role, same department
    hr_complete = await client.post(f"{TASKS}/{other}/complete", headers=w.hr)

    assert set(_ids(head_list)) == {tid, other}
    assert head_complete.status_code == 200 and hr_complete.status_code == 200
    assert set(_ids(manager_list)) == {tid, other}


@pytest.mark.asyncio
async def test_a_creator_still_sees_the_task_they_made_when_not_clocked_in(client, monkeypatch):
    """Only the assignee view is gated: Dana made it, so she keeps seeing it."""
    w = await _world(client, monkeypatch, "c3")
    tid = (await _task(client, w.dana.h, w.dispatch, "Dana's own", assigned_to_employee_id=w.bola.employee_id)).json()["id"]

    resp = await client.get(f"{TASKS}/{tid}", headers=w.dana.h)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_someone_who_is_not_the_assignee_still_gets_a_404_not_the_gate_message(client, monkeypatch):
    """The 409 is only for the assignee, who already knows the task exists; others learn nothing."""
    w = await _world(client, monkeypatch, "c4")
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    unclocked_stranger = await client.get(f"{TASKS}/{tid}", headers=w.bola.h)
    await _clock_in(client, w.bola)
    clocked_stranger = await client.get(f"{TASKS}/{tid}", headers=w.bola.h)

    assert unclocked_stranger.status_code == clocked_stranger.status_code == 404


@pytest.mark.asyncio
async def test_clocking_in_twice_does_not_change_what_the_gate_says(client, monkeypatch):
    """Clock-in is idempotent (one open record), so the gate stays open and nothing errors."""
    w = await _world(client, monkeypatch, "c5")
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)).json()["id"]

    await _clock_in(client, w.chidi)
    await _clock_in(client, w.chidi)

    assert (await client.get(f"{TASKS}/{tid}", headers=w.chidi.h)).status_code == 200
