"""HTTP-level tests for a department's performance summary (M12 slice E part 2).

Dispatch's Q3: its two KPI results are 70 (Lead Follow-up, weight 70) and 100
(Contract Paperwork, weight 30), so the headline is 79. Chidi has his design-example
quarter on Lead Follow-up (3 on time, 2 late, 1 not done = 66.67); Bola has one on-time
Contract Paperwork task (100); Dana and Tunde have no tasks. Team punctuality is over all
seven valid tasks: 4 on time, 2 late, 1 not done = 71.43.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.modules.kpis.models import KPI
from app.modules.organization.models import Employee
from app.modules.scoring.service import ScoringService
from tests.conftest import set_org_context
from tests.scoring.test_department_scores import _compute, _save_kpi_result
from tests.scoring.test_employee_scores import Q3_START, Q4_START, _chidis_quarter, _compute_q3, _done, _task, _two_kpis, at
from tests.tasks.test_tasks_router import _world

Q3 = {"period_start": "2026-07-01", "period_end": "2026-09-30"}


def summary_url(department_id: str) -> str:
    """The department summary route."""
    return f"/api/v1/departments/{department_id}/performance-summary"


async def _dispatch_quarter(client, db_session, w, save_scores: bool = True) -> tuple[str, str]:
    """Build Dispatch's Q3 as described in the module docstring; save its scores unless told not to.

    Returns:
        The ids of the Lead Follow-up and Contract Paperwork KPIs.
    """
    lead_follow_up, paperwork = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(update(KPI).values(created_at=datetime(2026, 6, 1, tzinfo=UTC)))
    await _save_kpi_result(db_session, w, lead_follow_up, "70")
    await _save_kpi_result(db_session, w, paperwork, "100")
    await _chidis_quarter(db_session, w, lead_follow_up)
    db_session.add(_task(w, "Bola's paperwork", paperwork, w.bola.employee_id, **_done(at(7, 10), at(7, 8))))
    await db_session.flush()
    if save_scores:
        await _compute_q3(db_session, w)
        await _compute(db_session, w)
    return lead_follow_up, paperwork


@pytest.mark.asyncio
async def test_tunde_reads_dispatch_two_numbers_side_by_side_and_his_people(client, monkeypatch, db_session):
    """Headline 79 (2 of 2), punctuality 71.43 (4/2/1), people best first, no-data people last."""
    w = await _world(client, monkeypatch, "dp1")
    await _dispatch_quarter(client, db_session, w)

    resp = await client.get(summary_url(w.dispatch), params=Q3, headers=w.tunde.h)

    assert resp.status_code == 200
    card = resp.json()
    assert card["department_id"] == w.dispatch and card["department_name"] == "Dispatch"
    assert (card["period_start"], card["period_end"]) == ("2026-07-01", "2026-09-30")
    assert card["is_final"] is False
    assert Decimal(card["kpi_results_score"]) == Decimal("79.00")
    assert (card["kpis_counted"], card["kpis_expected"]) == (2, 2)
    assert card["kpi_results_no_data_reason"] is None
    assert Decimal(card["punctuality_score"]) == Decimal("71.43")
    assert (card["punctuality_on_time"], card["punctuality_late"], card["punctuality_not_done"]) == (4, 2, 1)
    assert card["punctuality_no_data_reason"] is None

    names_and_scores = [(p["employee_name"], p["overall_score"]) for p in card["people"]]
    assert names_and_scores == [
        ("Bola Tester", "100.00"),
        ("Chidi Tester", "66.67"),
        ("Dana Tester", None),  # no tasks: no data, listed last, never 0
        ("Tunde Tester", None),
    ]
    assert [(p["kpis_counted"], p["kpis_expected"]) for p in card["people"]] == [(1, 2), (1, 2), (0, 2), (0, 2)]
    assert card["people_pagination"] == {
        "page": 1, "limit": 20, "total": 4, "total_pages": 1, "has_next": False, "has_previous": False,
    }


@pytest.mark.asyncio
async def test_who_may_open_a_department_and_everyone_else_gets_not_found(client, monkeypatch, db_session):
    """HR, its head and its manager open Dispatch; an employee and Sales' manager get the same 404 as a missing id."""
    w = await _world(client, monkeypatch, "dp2")
    await _dispatch_quarter(client, db_session, w)

    for allowed in (w.hr, w.tunde.h, w.dana.h):
        assert (await client.get(summary_url(w.dispatch), params=Q3, headers=allowed)).status_code == 200
    # Sam manages Sales, so Sales is his to open while Dispatch is not.
    assert (await client.get(summary_url(w.sales), params=Q3, headers=w.sam.h)).status_code == 200

    missing = await client.get(summary_url(str(uuid.uuid4())), params=Q3, headers=w.hr)
    assert missing.status_code == 404
    for refused in (w.chidi.h, w.sam.h):
        resp = await client.get(summary_url(w.dispatch), params=Q3, headers=refused)
        assert resp.status_code == 404
        assert resp.json() == missing.json()


@pytest.mark.asyncio
async def test_the_people_list_is_paged(client, monkeypatch, db_session):
    """Two per page: page 2 holds the last two, page 3 is empty, and a page size above 100 is refused."""
    w = await _world(client, monkeypatch, "dp3")
    await _dispatch_quarter(client, db_session, w)

    second = (await client.get(summary_url(w.dispatch), params={**Q3, "page": 2, "limit": 2}, headers=w.hr)).json()
    third = (await client.get(summary_url(w.dispatch), params={**Q3, "page": 3, "limit": 2}, headers=w.hr)).json()

    assert [p["employee_name"] for p in second["people"]] == ["Dana Tester", "Tunde Tester"]
    assert second["people_pagination"] == {
        "page": 2, "limit": 2, "total": 4, "total_pages": 2, "has_next": False, "has_previous": True,
    }
    assert third["people"] == []
    too_big = await client.get(summary_url(w.dispatch), params={**Q3, "limit": 101}, headers=w.hr)
    assert too_big.status_code == 422


@pytest.mark.asyncio
async def test_nothing_saved_yet_says_so_instead_of_showing_zeros(client, monkeypatch, db_session):
    """Before the nightly job has run: both numbers null with a reason, people still listed with no data."""
    w = await _world(client, monkeypatch, "dp4")
    await _dispatch_quarter(client, db_session, w, save_scores=False)

    card = (await client.get(summary_url(w.dispatch), params=Q3, headers=w.hr)).json()

    assert card["kpi_results_score"] is None and card["punctuality_score"] is None
    assert card["kpi_results_no_data_reason"] == "No scores have been worked out for this period yet."
    assert card["punctuality_no_data_reason"] == "No scores have been worked out for this period yet."
    assert (card["kpis_counted"], card["kpis_expected"]) == (0, 2)
    assert (card["punctuality_on_time"], card["punctuality_late"], card["punctuality_not_done"]) == (0, 0, 0)
    assert len(card["people"]) == 4 and all(p["overall_score"] is None for p in card["people"])


@pytest.mark.asyncio
async def test_a_department_with_no_kpis_and_no_tasks_has_a_reason_for_each_number(client, monkeypatch, db_session):
    """Sales has no KPIs and no tasks: each headline is null with its own reason, never 0."""
    w = await _world(client, monkeypatch, "dp5")
    await _dispatch_quarter(client, db_session, w)

    card = (await client.get(summary_url(w.sales), params=Q3, headers=w.sam.h)).json()

    assert card["kpi_results_score"] is None and card["punctuality_score"] is None
    assert card["kpi_results_no_data_reason"] == "This department has no KPIs in this period."
    assert card["punctuality_no_data_reason"] == "No task of this department had a deadline in this period."
    assert [p["employee_name"] for p in card["people"]] == ["Sam Tester"]


@pytest.mark.asyncio
async def test_a_closed_quarter_is_final_and_a_leaver_is_listed_only_if_they_have_a_score(
    client, monkeypatch, db_session
):
    """After the freeze: is_final. Bola left but has a Q3 score so is still listed; Dana left with none, so is not."""
    w = await _world(client, monkeypatch, "dp6")
    await _dispatch_quarter(client, db_session, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await ScoringService(db_session).finalize_employee_scores(org_id, Q3_START, Q4_START, Q4_START)
    await ScoringService(db_session).finalize_department_scores(org_id, Q3_START, Q4_START, Q4_START)
    leavers = [uuid.UUID(w.bola.employee_id), uuid.UUID(w.dana.employee_id)]
    await db_session.execute(update(Employee).where(Employee.id.in_(leavers)).values(status="inactive"))

    card = (await client.get(summary_url(w.dispatch), params=Q3, headers=w.hr)).json()

    assert card["is_final"] is True
    assert [p["employee_name"] for p in card["people"]] == ["Bola Tester", "Chidi Tester", "Tunde Tester"]
