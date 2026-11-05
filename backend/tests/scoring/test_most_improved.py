"""HTTP-level tests for Most Improved (M12 slice F part 2).

Rows for two quarters are inserted directly, as the nightly job would have left them:
Q2 (1 April to 30 June) is the quarter before the asked Q3 (1 July to 30 September).
"""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.modules.organization.models import Employee
from app.modules.scoring.models import DepartmentScore, EmployeeKPIScore
from tests.conftest import set_org_context
from tests.scoring.test_department_performance import Q3
from tests.scoring.test_employee_scores import _two_kpis
from tests.tasks.test_tasks_router import _member, _world

URL = "/api/v1/company-performance-summary/most-improved"
Q2_DAYS = (date(2026, 4, 1), date(2026, 6, 30))
Q3_DAYS = (date(2026, 7, 1), date(2026, 9, 30))


def _person_row(w, employee_id: str, kpi_id: str, days, score: str, tasks: int) -> EmployeeKPIScore:
    """A person's saved row on one KPI: `tasks` valid tasks, a third of them not done (counts only need to add up)."""
    not_done = tasks // 3
    return EmployeeKPIScore(
        organization_id=uuid.UUID(w.owner["organization"]["id"]),
        employee_id=uuid.UUID(employee_id),
        kpi_id=uuid.UUID(kpi_id),
        period_start=days[0],
        period_end=days[1],
        tasks_on_time=tasks - not_done,
        tasks_late=0,
        tasks_not_done=not_done,
        score_percentage=Decimal(score),
        weight_used=Decimal("70"),
    )


def _department_row(w, department_id: str, days, punctuality: str, tasks: int) -> DepartmentScore:
    """A department's saved row with `tasks` valid tasks behind its punctuality."""
    return DepartmentScore(
        organization_id=uuid.UUID(w.owner["organization"]["id"]),
        department_id=uuid.UUID(department_id),
        period_start=days[0],
        period_end=days[1],
        punctuality_on_time=tasks,
        punctuality_late=0,
        punctuality_not_done=0,
        punctuality_score=Decimal(punctuality),
    )


async def _seed(client, db_session, w, people: list) -> str:
    """Save Q2 and Q3 rows for people given as [(employee, (q2_score, q2_tasks, q3_score, q3_tasks))]."""
    lead_follow_up, _ = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    for employee, (before, before_tasks, now, now_tasks) in people:
        db_session.add(_person_row(w, employee.employee_id, lead_follow_up, Q2_DAYS, before, before_tasks))
        db_session.add(_person_row(w, employee.employee_id, lead_follow_up, Q3_DAYS, now, now_tasks))
    await db_session.flush()
    return lead_follow_up


@pytest.mark.asyncio
async def test_the_biggest_gains_are_listed_with_how_they_were_earned(client, monkeypatch, db_session):
    """Chidi 40 to 70 (+30) before Bola 60 to 65 (+5); Dana's 9 tasks last quarter keep her off the list."""
    w = await _world(client, monkeypatch, "mi1")
    await _seed(client, db_session, w, [
        (w.chidi, ("40", 12, "70", 15)),
        (w.bola, ("60", 10, "65", 10)),
        (w.dana, ("10", 9, "100", 30)),
    ])
    db_session.add(_department_row(w, w.dispatch, Q2_DAYS, "60", 20))
    db_session.add(_department_row(w, w.dispatch, Q3_DAYS, "75", 25))
    db_session.add(_department_row(w, w.sales, Q3_DAYS, "90", 40))  # no Q2 row: nothing to compare with
    await db_session.flush()

    resp = await client.get(URL, params=Q3, headers=w.hr)

    assert resp.status_code == 200
    board = resp.json()
    assert (board["period_start"], board["previous_period_start"], board["previous_period_end"]) == (
        "2026-07-01", "2026-04-01", "2026-06-30",
    )
    assert board["min_valid_tasks"] == 10
    people = [(p["name"], p["previous_score"], p["current_score"], p["change_in_points"],
               p["previous_tasks"], p["current_tasks"]) for p in board["people"]]
    assert people == [
        ("Chidi Tester", "40.00", "70.00", "30.00", 12, 15),
        ("Bola Tester", "60.00", "65.00", "5.00", 10, 10),
    ]
    assert [(d["name"], d["change_in_points"], d["previous_tasks"], d["current_tasks"])
            for d in board["departments"]] == [("Dispatch", "15.00", 20, 25)]


@pytest.mark.asyncio
async def test_only_the_top_three_are_listed_and_a_deleted_person_makes_room_for_the_next(
    client, monkeypatch, db_session
):
    """Four improved: the smallest gain is dropped; deleting the biggest brings the fourth back."""
    w = await _world(client, monkeypatch, "mi2")
    await _seed(client, db_session, w, [
        (w.chidi, ("40", 10, "80", 10)),  # +40
        (w.bola, ("40", 10, "70", 10)),  # +30
        (w.dana, ("40", 10, "60", 10)),  # +20
        (w.tunde, ("40", 10, "50", 10)),  # +10
    ])

    first = (await client.get(URL, params=Q3, headers=w.hr)).json()
    assert [p["name"] for p in first["people"]] == ["Chidi Tester", "Bola Tester", "Dana Tester"]

    await db_session.execute(
        update(Employee).where(Employee.id == uuid.UUID(w.chidi.employee_id)).values(deleted_at=datetime.now(UTC))
    )
    second = (await client.get(URL, params=Q3, headers=w.hr)).json()
    assert [p["name"] for p in second["people"]] == ["Bola Tester", "Dana Tester", "Tunde Tester"]


@pytest.mark.asyncio
async def test_only_hr_and_executives_may_open_it(client, monkeypatch, db_session):
    """An executive can; a head, a manager and an employee get the same 404."""
    w = await _world(client, monkeypatch, "mi3")
    positions = (await client.get("/api/v1/positions", headers=w.hr)).json()["data"]
    executive = await _member(client, monkeypatch, w.hr, "tk_exec_mi3@example.com", "business_executive",
                              positions[0]["id"], "Eve")

    assert (await client.get(URL, params=Q3, headers=executive.h)).status_code == 200
    bodies = []
    for refused in (w.tunde.h, w.dana.h, w.chidi.h):
        resp = await client.get(URL, params=Q3, headers=refused)
        assert resp.status_code == 404
        bodies.append(resp.json())
    assert bodies[0] == bodies[1] == bodies[2]


@pytest.mark.asyncio
async def test_with_nothing_saved_both_lists_are_simply_empty(client, monkeypatch, db_session):
    """Not an error: the screen shows 'nobody qualifies yet'."""
    w = await _world(client, monkeypatch, "mi4")

    resp = await client.get(URL, params=Q3, headers=w.hr)

    assert resp.status_code == 200
    assert resp.json()["people"] == [] and resp.json()["departments"] == []
