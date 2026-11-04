"""HTTP-level tests for the live custom date range (M12 slice F part 3).

Uses Dispatch's usual Q3 tasks: Bola's one on-time task (due 10 July) and Chidi's six valid
ones (due 10 July, 20 July, 5 August, 20 August, 15 September, and 1 September held back
three days so its real deadline is 4 September).
"""
from decimal import Decimal

import pytest

from tests.scoring.test_department_performance import _dispatch_quarter
from tests.tasks.test_tasks_router import _member, _world

URL = "/api/v1/company-performance-summary/custom-range"


def window(first: str, last: str) -> dict:
    """The query parameters for a range."""
    return {"period_start": first, "period_end": last}


@pytest.mark.asyncio
async def test_a_live_range_covering_q3_gives_the_same_counts_as_the_saved_quarter(client, monkeypatch, db_session):
    """Nothing was saved at all (no job ran), yet the live view finds 4 on time, 2 late, 1 not done."""
    w = await _world(client, monkeypatch, "cr1")
    await _dispatch_quarter(client, db_session, w, save_scores=False)

    resp = await client.get(URL, params=window("2026-07-01", "2026-09-30"), headers=w.hr)

    assert resp.status_code == 200
    board = resp.json()
    assert board["is_live"] is True and "live" in board["label"]
    assert (board["period_start"], board["period_end"]) == ("2026-07-01", "2026-09-30")
    assert Decimal(board["punctuality_score"]) == Decimal("71.43")
    assert (board["punctuality_on_time"], board["punctuality_late"], board["punctuality_not_done"]) == (4, 2, 1)
    by_name = {d["department_name"]: d for d in board["departments"]}
    assert Decimal(by_name["Dispatch"]["punctuality_score"]) == Decimal("71.43")
    assert by_name["Sales"]["punctuality_score"] is None  # no tasks: no data, not 0
    assert (by_name["Sales"]["punctuality_on_time"], by_name["Sales"]["punctuality_late"]) == (0, 0)
    assert [d["department_name"] for d in board["departments"]] == ["Dispatch", "Sales"]


@pytest.mark.asyncio
async def test_a_window_inside_the_quarter_counts_only_tasks_whose_deadline_falls_in_it(client, monkeypatch, db_session):
    """August holds two deadlines. The 5 August task was finished on 9 August (late). The 20 August task
    was only finished on 25 September, after the window ended, so inside this window it is not done."""
    w = await _world(client, monkeypatch, "cr2")
    await _dispatch_quarter(client, db_session, w, save_scores=False)

    board = (await client.get(URL, params=window("2026-08-01", "2026-08-31"), headers=w.hr)).json()

    assert (board["punctuality_on_time"], board["punctuality_late"], board["punctuality_not_done"]) == (0, 1, 1)
    assert Decimal(board["punctuality_score"]) == Decimal("25.00")


@pytest.mark.asyncio
async def test_a_window_with_no_deadlines_is_no_data_with_a_reason(client, monkeypatch, db_session):
    """January 2025 has no tasks: null score and a reason, not 0."""
    w = await _world(client, monkeypatch, "cr3")
    await _dispatch_quarter(client, db_session, w, save_scores=False)

    board = (await client.get(URL, params=window("2025-01-01", "2025-01-31"), headers=w.hr)).json()

    assert board["punctuality_score"] is None
    assert board["punctuality_no_data_reason"] == "No task had a deadline in this range."


@pytest.mark.asyncio
async def test_the_range_must_be_complete_in_order_and_at_most_a_year(client, monkeypatch, db_session):
    """No dates, one date, backwards, and two years are all 422."""
    w = await _world(client, monkeypatch, "cr4")

    assert (await client.get(URL, headers=w.hr)).status_code == 422
    assert (await client.get(URL, params={"period_start": "2026-01-01"}, headers=w.hr)).status_code == 422
    assert (await client.get(URL, params=window("2026-03-20", "2026-01-15"), headers=w.hr)).status_code == 422
    assert (await client.get(URL, params=window("2025-01-01", "2026-12-31"), headers=w.hr)).status_code == 422
    assert (await client.get(URL, params=window("2026-01-01", "2026-12-31"), headers=w.hr)).status_code == 200


@pytest.mark.asyncio
async def test_only_hr_and_executives_may_open_it(client, monkeypatch, db_session):
    """An executive can; a head, a manager and an employee get the same 404."""
    w = await _world(client, monkeypatch, "cr5")
    positions = (await client.get("/api/v1/positions", headers=w.hr)).json()["data"]
    executive = await _member(client, monkeypatch, w.hr, "tk_exec_cr5@example.com", "business_executive",
                              positions[0]["id"], "Eve")

    assert (await client.get(URL, params=window("2026-07-01", "2026-09-30"), headers=executive.h)).status_code == 200
    bodies = []
    for refused in (w.tunde.h, w.dana.h, w.chidi.h):
        resp = await client.get(URL, params=window("2026-07-01", "2026-09-30"), headers=refused)
        assert resp.status_code == 404
        bodies.append(resp.json())
    assert bodies[0] == bodies[1] == bodies[2]
