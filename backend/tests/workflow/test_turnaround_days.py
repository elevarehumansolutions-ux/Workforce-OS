"""A workflow step's turnaround in working days (08_DECISIONS.md 2026-11-14).

Scenario: nobody wants to calculate hours. "2 days" means two full working days of the company's own
hours: 16 hours at 9 to 5, 18 at 8 to 5, and it stays right if the company changes its hours later.
"""
from datetime import datetime

import pytest

from app.modules.workflow.deadlines import DEFAULT_WEEK, WorkingWeek, turnaround_in_hours
from tests.tasks.test_tasks_router import _world
from tests.workflow.test_instance_start import _start, _tasks_of, _template
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create

HOURS = "/api/v1/working-hours"
STEPS = "/api/v1/workflow-steps"


# -- the conversion on its own ---------------------------------------------------------------------


def test_hours_are_used_as_given_and_days_become_the_companys_working_days():
    assert turnaround_in_hours(5, None, DEFAULT_WEEK) == 5
    assert turnaround_in_hours(None, 2, DEFAULT_WEEK) == 16  # 9 to 5 is 8 hours a day
    assert turnaround_in_hours(None, 2, WorkingWeek(8, 17)) == 18  # 8 to 5 is 9 hours a day
    assert turnaround_in_hours(None, None, DEFAULT_WEEK) is None


# -- saving a step in days -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_step_can_be_given_in_days(client, monkeypatch):
    w = await _world(client, monkeypatch, "td1")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    added = await _add(client, w.hr, template["id"], "Review", w.sales, default_turnaround_days=2)

    assert added.status_code == 200, added.text
    body = added.json()
    assert (body["default_turnaround_days"], body["default_turnaround_hours"]) == (2, None)


@pytest.mark.asyncio
async def test_hours_and_days_together_are_refused(client, monkeypatch):
    w = await _world(client, monkeypatch, "td2")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    added = await _add(client, w.hr, template["id"], "Review", w.sales, default_turnaround_hours=8, default_turnaround_days=1)
    assert added.status_code == 422

    step = (await _add(client, w.hr, template["id"], "Review", w.sales, default_turnaround_hours=8)).json()
    both = await client.patch(
        f"{STEPS}/{step['id']}", json={"default_turnaround_hours": 8, "default_turnaround_days": 1}, headers=w.hr
    )
    assert both.status_code == 422


@pytest.mark.asyncio
async def test_a_zero_or_negative_number_of_days_is_refused(client, monkeypatch):
    w = await _world(client, monkeypatch, "td3")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    assert (await _add(client, w.hr, template["id"], "Review", w.sales, default_turnaround_days=0)).status_code == 422
    assert (await _add(client, w.hr, template["id"], "Review", w.sales, default_turnaround_days=-1)).status_code == 422


@pytest.mark.asyncio
async def test_changing_the_unit_is_one_edit_and_the_other_one_is_cleared(client, monkeypatch):
    w = await _world(client, monkeypatch, "td4")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    step = (await _add(client, w.hr, template["id"], "Review", w.sales, default_turnaround_hours=24)).json()

    to_days = await client.patch(f"{STEPS}/{step['id']}", json={"default_turnaround_days": 3}, headers=w.hr)
    assert (to_days.json()["default_turnaround_days"], to_days.json()["default_turnaround_hours"]) == (3, None)

    back = await client.patch(f"{STEPS}/{step['id']}", json={"default_turnaround_hours": 6}, headers=w.hr)
    assert (back.json()["default_turnaround_days"], back.json()["default_turnaround_hours"]) == (None, 6)

    cleared = await client.patch(f"{STEPS}/{step['id']}", json={"default_turnaround_hours": None}, headers=w.hr)
    assert (cleared.json()["default_turnaround_days"], cleared.json()["default_turnaround_hours"]) == (None, None)


# -- the deadline a case gets ----------------------------------------------------------------------


def _due(task: dict) -> datetime:
    return datetime.fromisoformat(task["due_at"])


@pytest.mark.asyncio
async def test_two_days_is_two_full_working_days_of_the_company(client, monkeypatch):
    """8 to 5 is 9 hours a day, so 2 days gives the same deadline as an 18-hour step; later at 9 to 5, as 16 hours."""
    w = await _world(client, monkeypatch, "td5")
    in_days = await _template(client, w, ("Hand-off", w.sales, {"default_turnaround_days": 2}))
    eighteen = await _template(client, w, ("Hand-off", w.sales, {"default_turnaround_hours": 18}))
    sixteen = await _template(client, w, ("Hand-off", w.sales, {"default_turnaround_hours": 16}))

    assert (await client.put(HOURS, json={"start_hour": 8, "end_hour": 17, "work_days": [0, 1, 2, 3, 4]}, headers=w.hr)).status_code == 200
    days_case = (await _start(client, w.chidi.h, in_days["id"])).json()
    hours_case = (await _start(client, w.chidi.h, eighteen["id"])).json()
    days_due = _due((await _tasks_of(client, w, days_case["id"]))[0])
    hours_due = _due((await _tasks_of(client, w, hours_case["id"]))[0])
    # The two cases start a moment apart; the same working-hours count gives the same deadline.
    assert abs((days_due - hours_due).total_seconds()) < 60

    # The company moves to 9 to 5: the same "2 days" step is now 16 hours long, no edit needed.
    assert (await client.put(HOURS, json={"start_hour": 9, "end_hour": 17, "work_days": [0, 1, 2, 3, 4]}, headers=w.hr)).status_code == 200
    later_case = (await _start(client, w.chidi.h, in_days["id"])).json()
    sixteen_case = (await _start(client, w.chidi.h, sixteen["id"])).json()
    later_due = _due((await _tasks_of(client, w, later_case["id"]))[0])
    sixteen_due = _due((await _tasks_of(client, w, sixteen_case["id"]))[0])
    assert abs((later_due - sixteen_due).total_seconds()) < 60
