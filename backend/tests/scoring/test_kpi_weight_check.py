"""The quarter-start KPI weight check: a reminder to HR, once per department, never a block.

Scenario: Adaeze's Dispatch department has one KPI weighted 70%. When the new quarter's first
night runs, she is told 30% of Dispatch is not measured. She is told once, scoring carries on,
and a department at exactly 100% never triggers a reminder.
"""
from datetime import timedelta

import pytest

from tests.scoring.test_employee_scores import _two_kpis
from tests.scoring.test_nightly_job import JUST_AFTER_Q3, _night, _old_company
from tests.tasks.test_tasks_router import KPIS, NOTIFICATIONS, _world

WEIGHT_TITLE = "A department's KPI weights are not at 100%"


async def _weight_reminders(client, w) -> list:
    """The reminders HR has received."""
    rows = (await client.get(NOTIFICATIONS, headers=w.hr)).json()
    return [row for row in rows if row["title"] == WEIGHT_TITLE]


async def _one_kpi(client, w, weight: int) -> None:
    created = await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "Lead Follow-up", "weight": weight}, headers=w.hr
    )
    assert created.status_code == 200


@pytest.mark.asyncio
async def test_a_department_short_of_100_is_reported_to_hr_once_for_the_quarter(client, monkeypatch, db_session):
    """70% allocated: HR is told 30% is not measured, linked to the department, and not told again the next night."""
    w = await _world(client, monkeypatch, "wc1")
    await _one_kpi(client, w, 70)
    await _old_company(db_session, w)

    first = await _night(db_session, w, JUST_AFTER_Q3)
    await _night(db_session, w, JUST_AFTER_Q3 + timedelta(days=1))

    reminders = await _weight_reminders(client, w)
    assert len(reminders) == 1
    assert "70%" in reminders[0]["body"] and "30%" in reminders[0]["body"]
    assert reminders[0]["link_type"] == "department"
    assert reminders[0]["link_id"] == w.dispatch
    assert first["closed_previous_period"] is True  # scoring itself still ran


@pytest.mark.asyncio
async def test_a_department_at_exactly_100_gets_no_reminder(client, monkeypatch, db_session):
    """Nothing to say when the weights are complete."""
    w = await _world(client, monkeypatch, "wc2")
    await _two_kpis(client, w)  # 70 + 30
    await _old_company(db_session, w)

    await _night(db_session, w, JUST_AFTER_Q3)

    assert await _weight_reminders(client, w) == []


@pytest.mark.asyncio
async def test_a_department_with_no_kpis_is_not_a_weight_problem(client, monkeypatch, db_session):
    """No KPIs at all shows as 'no KPIs' elsewhere; the weight reminder is only for a part-filled set."""
    w = await _world(client, monkeypatch, "wc3")
    await _old_company(db_session, w)

    await _night(db_session, w, JUST_AFTER_Q3)

    assert await _weight_reminders(client, w) == []


@pytest.mark.asyncio
async def test_a_company_younger_than_the_quarter_is_not_reminded_yet(client, monkeypatch, db_session):
    """Created after the quarter began: still drafting its first KPIs, so no reminder tonight."""
    w = await _world(client, monkeypatch, "wc4")
    await _one_kpi(client, w, 70)
    await _old_company(db_session, w, created=JUST_AFTER_Q3)

    await _night(db_session, w, JUST_AFTER_Q3 + timedelta(days=1))

    assert await _weight_reminders(client, w) == []

