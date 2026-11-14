"""The company's working week: GET and PUT /working-hours, and workflow deadlines using it
(08_DECISIONS.md 2026-11-14).

Scenario: Emmanuel's boss wants 8 to 5, not 9 to 5. HR sets it once; any member can read it; and a case
started afterwards gets deadlines counted in those hours.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import commit_like_production
from tests.tasks.test_tasks_router import _world
from tests.workflow.test_instance_start import _start, _tasks_of, _template

HOURS = "/api/v1/working-hours"
LAGOS = ZoneInfo("Africa/Lagos")


@pytest.mark.asyncio
async def test_a_company_that_never_set_it_has_nine_to_five_monday_to_friday(client, monkeypatch):
    w = await _world(client, monkeypatch, "wh1")

    resp = await client.get(HOURS, headers=w.hr)

    assert resp.status_code == 200
    assert resp.json() == {"start_hour": 9, "end_hour": 17, "work_days": [0, 1, 2, 3, 4], "hours_per_day": 8}


@pytest.mark.asyncio
async def test_hr_sets_the_week_and_everyone_reads_it(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "wh2")
    commit_like_production(db_session, monkeypatch)

    saved = await client.put(HOURS, json={"start_hour": 8, "end_hour": 17, "work_days": [5, 0, 1, 2, 3, 4]}, headers=w.hr)

    assert saved.status_code == 200, saved.text
    assert saved.json() == {"start_hour": 8, "end_hour": 17, "work_days": [0, 1, 2, 3, 4, 5], "hours_per_day": 9}
    # An ordinary employee reads the same answer (a step form needs to know how long "1 day" is).
    seen = await client.get(HOURS, headers=w.chidi.h)
    assert seen.status_code == 200 and seen.json()["hours_per_day"] == 9


@pytest.mark.asyncio
async def test_only_an_hr_administrator_may_change_it(client, monkeypatch):
    w = await _world(client, monkeypatch, "wh3")
    body = {"start_hour": 8, "end_hour": 17, "work_days": [0, 1, 2, 3, 4]}

    assert (await client.put(HOURS, json=body, headers=w.dana.h)).status_code == 403  # a manager
    assert (await client.put(HOURS, json=body, headers=w.chidi.h)).status_code == 403  # an employee
    assert (await client.get(HOURS, headers=w.hr)).json()["start_hour"] == 9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"start_hour": 17, "end_hour": 9, "work_days": [0, 1]},  # ends before it starts
        {"start_hour": 9, "end_hour": 9, "work_days": [0, 1]},  # a day of no length
        {"start_hour": 9, "end_hour": 17, "work_days": []},  # no working days
        {"start_hour": 9, "end_hour": 17, "work_days": [0, 7]},  # there is no day 7
        {"start_hour": 9, "end_hour": 17, "work_days": [1, 1]},  # a day listed twice
        {"start_hour": -1, "end_hour": 17, "work_days": [0]},
        {"start_hour": 9, "end_hour": 24, "work_days": [0]},
    ],
)
async def test_a_nonsense_week_is_refused_and_nothing_changes(client, monkeypatch, body):
    w = await _world(client, monkeypatch, "wh4")

    assert (await client.put(HOURS, json=body, headers=w.hr)).status_code == 422
    assert (await client.get(HOURS, headers=w.hr)).json()["start_hour"] == 9


@pytest.mark.asyncio
async def test_another_companys_week_is_not_touched(client, monkeypatch):
    mine = await _world(client, monkeypatch, "wh5")
    other = await _world(client, monkeypatch, "wh6")

    await client.put(HOURS, json={"start_hour": 7, "end_hour": 15, "work_days": [0, 1, 2]}, headers=mine.hr)

    assert (await client.get(HOURS, headers=other.hr)).json()["start_hour"] == 9


@pytest.mark.asyncio
async def test_a_case_started_after_the_change_counts_in_the_companys_hours(client, monkeypatch):
    """One working day only, Sunday 10:00 to 12:00: a one-hour step can only be due then, whatever 'now' is."""
    w = await _world(client, monkeypatch, "wh7")
    saved = await client.put(HOURS, json={"start_hour": 10, "end_hour": 12, "work_days": [6]}, headers=w.hr)
    assert saved.status_code == 200
    template = await _template(client, w, ("Sales hand-off", w.sales, {"default_turnaround_hours": 1}))

    started = (await _start(client, w.chidi.h, template["id"])).json()

    due = datetime.fromisoformat((await _tasks_of(client, w, started["id"]))[0]["due_at"]).astimezone(LAGOS)
    assert due.weekday() == 6
    assert due.hour in (10, 11, 12) and (due.hour, due.minute) <= (12, 0)
