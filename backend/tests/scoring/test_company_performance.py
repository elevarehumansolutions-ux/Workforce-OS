"""HTTP-level tests for the company dashboard (M12 slice F part 1).

Dispatch (share 60) has the usual Q3: KPI results 70 and 100 give 79, punctuality over 7 tasks.
Sales (share 40) has one KPI with a result of 90 and no tasks. Headline: (79 x 60 + 90 x 40) / 100 = 83.40.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.modules.organization.models import Department
from app.modules.scoring.service import ScoringService
from tests.conftest import set_org_context
from tests.scoring.test_department_performance import Q3, _dispatch_quarter
from tests.scoring.test_department_scores import _compute, _save_kpi_result
from tests.scoring.test_employee_scores import Q3_START, Q4_START, _compute_q3
from tests.tasks.test_tasks_router import KPIS, _member, _world

COMPANY = "/api/v1/company-performance-summary"


async def _two_department_company(client, monkeypatch, db_session, tag: str, sales_share="40"):
    """Dispatch and Sales as described in the module docstring, with their Q3 rows saved."""
    w = await _world(client, monkeypatch, tag)
    await _dispatch_quarter(client, db_session, w, save_scores=False)
    sales_kpi = (await client.post(
        KPIS, json={"department_id": w.sales, "name": "Renewals", "weight": 100}, headers=w.hr
    )).json()["id"]
    await _save_kpi_result(db_session, w, sales_kpi, "90")
    await set_org_context(db_session, w.owner["organization"]["id"])
    await _set_share(db_session, w.dispatch, "60")
    await _set_share(db_session, w.sales, sales_share)
    await _compute_q3(db_session, w)
    await _compute(db_session, w)
    return w


async def _set_share(db_session, department_id: str, share):
    """Set a department's revenue share directly (None clears it)."""
    value = None if share is None else Decimal(share)
    await db_session.execute(
        update(Department).where(Department.id == uuid.UUID(department_id)).values(revenue_allocation_percentage=value)
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_hr_reads_the_headline_the_pooled_punctuality_the_departments_and_the_trend(
    client, monkeypatch, db_session
):
    """83.40 from 2 of 2 departments, punctuality 71.43 over 7 tasks, Dispatch listed before Sales, a 4-quarter trend."""
    w = await _two_department_company(client, monkeypatch, db_session, "cp1")

    resp = await client.get(COMPANY, params=Q3, headers=w.hr)

    assert resp.status_code == 200
    board = resp.json()
    assert (board["period_start"], board["period_end"]) == ("2026-07-01", "2026-09-30")
    assert Decimal(board["headline_score"]) == Decimal("83.40")
    assert (board["departments_counted"], board["departments_expected"]) == (2, 2)
    assert board["headline_is_plain_average"] is False and board["headline_no_data_reason"] is None
    assert Decimal(board["punctuality_score"]) == Decimal("71.43")
    assert (board["punctuality_on_time"], board["punctuality_late"], board["punctuality_not_done"]) == (4, 2, 1)

    lines = [(d["department_name"], d["revenue_share"], d["kpi_results_score"], d["counted_in_headline"])
             for d in board["departments"]]
    assert lines == [("Dispatch", "60.00", "79.00", True), ("Sales", "40.00", "90.00", True)]

    # The trend: this quarter and the three before it, oldest first; only this one has saved rows.
    assert [(t["period_start"], t["period_end"]) for t in board["trend"]] == [
        ("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30"),
        ("2026-07-01", "2026-09-30"),
    ]
    assert [t["headline_score"] for t in board["trend"][:3]] == [None, None, None]
    assert Decimal(board["trend"][3]["headline_score"]) == Decimal("83.40")
    assert board["trend"][3]["departments_counted"] == 2


@pytest.mark.asyncio
async def test_a_department_without_a_share_is_left_out_and_the_headline_says_how_many_counted(
    client, monkeypatch, db_session
):
    """Sales has a result but no share: headline is Dispatch's 79 alone, '1 of 2 counted'."""
    w = await _two_department_company(client, monkeypatch, db_session, "cp2", sales_share=None)

    board = (await client.get(COMPANY, params=Q3, headers=w.hr)).json()

    assert Decimal(board["headline_score"]) == Decimal("79.00")
    assert (board["departments_counted"], board["departments_expected"]) == (1, 2)
    counted = {d["department_name"]: d["counted_in_headline"] for d in board["departments"]}
    assert counted == {"Dispatch": True, "Sales": False}
    assert board["departments"][-1]["revenue_share"] is None  # no share listed last


@pytest.mark.asyncio
async def test_only_hr_and_executives_may_open_the_company_view(client, monkeypatch, db_session):
    """An executive can; a head, a manager and an employee get the same 404."""
    w = await _two_department_company(client, monkeypatch, db_session, "cp3")
    positions = (await client.get("/api/v1/positions", headers=w.hr)).json()["data"]
    executive = await _member(client, monkeypatch, w.hr, "tk_exec_cp3@example.com", "business_executive",
                              positions[0]["id"], "Eve")

    assert (await client.get(COMPANY, params=Q3, headers=executive.h)).status_code == 200

    bodies = []
    for refused in (w.tunde.h, w.dana.h, w.chidi.h):
        resp = await client.get(COMPANY, params=Q3, headers=refused)
        assert resp.status_code == 404
        bodies.append(resp.json())
    assert bodies[0] == bodies[1] == bodies[2]


@pytest.mark.asyncio
async def test_before_anything_is_saved_both_numbers_say_so_instead_of_showing_zeros(client, monkeypatch, db_session):
    """No department rows yet: null scores with a reason, still a 4-point trend of nulls."""
    w = await _world(client, monkeypatch, "cp4")

    board = (await client.get(COMPANY, params=Q3, headers=w.hr)).json()

    assert board["headline_score"] is None and board["punctuality_score"] is None
    assert board["headline_no_data_reason"] == "No scores have been worked out for this period yet."
    assert board["punctuality_no_data_reason"] == board["headline_no_data_reason"]
    assert (board["departments_counted"], board["departments_expected"]) == (0, 0)
    assert board["departments"] == [] and len(board["trend"]) == 4


@pytest.mark.asyncio
async def test_a_closed_quarter_keeps_the_shares_it_was_scored_with(client, monkeypatch, db_session):
    """After the freeze, HR changing Dispatch's share to 10 does not move the closed quarter's headline."""
    w = await _two_department_company(client, monkeypatch, db_session, "cp5")
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await ScoringService(db_session).finalize_department_scores(org_id, Q3_START, Q4_START, Q4_START)
    await _set_share(db_session, w.dispatch, "10")

    board = (await client.get(COMPANY, params=Q3, headers=w.hr)).json()

    assert board["is_final"] is True
    assert Decimal(board["headline_score"]) == Decimal("83.40")
    assert board["departments"][0]["revenue_share"] == "60.00"
