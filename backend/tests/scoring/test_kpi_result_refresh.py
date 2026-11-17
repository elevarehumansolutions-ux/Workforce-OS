"""Tests for to-do 71: saving a KPI result brings the department's figures up to date at once.

Before this, the department's "did it hit its goals" number waited for the nightly job, so HR
typed a result and saw nothing change.
"""
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.scoring.service import ScoringService
from tests.conftest import set_org_context
from tests.scoring.test_department_performance import summary_url
from tests.tasks.test_tasks_router import KPIS, _world


async def _kpi_with_target(client, w) -> str:
    """A manual KPI with a target of 100, so a typed result becomes a percentage."""
    created = await client.post(
        KPIS,
        json={"department_id": w.dispatch, "name": "Lead Follow-up", "weight": 100, "target_value": 100},
        headers=w.hr,
    )
    assert created.status_code == 200
    return created.json()["id"]


def _this_calendar_quarter() -> tuple[date, date]:
    """First and last day of the calendar quarter that today falls in (the test company's fiscal year is the calendar year)."""
    today = date.today()
    first_month = 3 * ((today.month - 1) // 3) + 1
    first = date(today.year, first_month, 1)
    next_first = date(today.year + 1, 1, 1) if first_month == 10 else date(today.year, first_month + 3, 1)
    return first, next_first - timedelta(days=1)


@pytest.mark.asyncio
async def test_saving_a_result_updates_the_departments_goals_number_straight_away(client, monkeypatch):
    """No nightly job runs in this test: the number appears because the save itself refreshed it."""
    w = await _world(client, monkeypatch, "kr1")
    lead_follow_up = await _kpi_with_target(client, w)
    first, last = _this_calendar_quarter()

    before = await client.get(summary_url(w.dispatch), headers=w.hr)
    saved = await client.post(
        f"{KPIS}/{lead_follow_up}/scores",
        json={"period_start": first.isoformat(), "period_end": last.isoformat(), "actual_value": 80},
        headers=w.hr,
    )
    after = await client.get(summary_url(w.dispatch), headers=w.hr)

    assert before.status_code == 200 and before.json()["kpi_results_score"] is None
    assert saved.status_code == 200 and saved.json()["score_percentage"] is not None
    assert after.json()["kpi_results_score"] == saved.json()["score_percentage"]
    assert after.json()["kpis_counted"] == 1


@pytest.mark.asyncio
async def test_a_second_save_in_the_same_quarter_changes_the_number_again(client, monkeypatch):
    """Correcting a typed result is reflected at once too."""
    w = await _world(client, monkeypatch, "kr2")
    lead_follow_up = await _kpi_with_target(client, w)
    first, last = _this_calendar_quarter()
    period = {"period_start": first.isoformat(), "period_end": last.isoformat()}

    await client.post(f"{KPIS}/{lead_follow_up}/scores", json={**period, "actual_value": 50}, headers=w.hr)
    first_view = await client.get(summary_url(w.dispatch), headers=w.hr)
    await client.post(f"{KPIS}/{lead_follow_up}/scores", json={**period, "actual_value": 90}, headers=w.hr)
    second_view = await client.get(summary_url(w.dispatch), headers=w.hr)

    assert first_view.json()["kpi_results_score"] != second_view.json()["kpi_results_score"]


@pytest.mark.asyncio
async def test_a_result_for_another_period_leaves_the_open_quarter_alone(client, monkeypatch, db_session):
    """A result that is not for the open quarter refreshes nothing."""
    w = await _world(client, monkeypatch, "kr3")
    await set_org_context(db_session, w.owner["organization"]["id"])

    refreshed = await ScoringService(db_session).refresh_departments_after_result(
        uuid.UUID(w.owner["organization"]["id"]), date(2030, 1, 1), datetime.now(UTC)
    )

    assert refreshed is False
