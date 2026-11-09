"""The money view of a case through the API: the figure, the deadline, at risk and lost.

Scenario: Chidi starts "Zenith Ltd: source a CFO" with a N2,000,000 fee and a final deadline.
When the first task lags the fee is at risk; when the case is cancelled, or the deadline passes
unfinished, it is lost. A case started without a figure shows nothing.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.modules.tasks.models import Task
from app.modules.workflow.models import WorkflowInstance
from tests.tasks.test_tasks_router import _world
from tests.workflow.test_instance_start import INSTANCES, _template

FEE = "2000000.00"
SUMMARY = INSTANCES + "/value-summary"


def _later(days: int = 20) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def _case(client, w, *, value=FEE, deadline=None, starter=None):
    """A one-step template and a case on it; returns the case JSON."""
    template = await _template(client, w, ("Shortlist candidates", w.dispatch, {}))
    body = {"template_id": template["id"], "subject": "Zenith Ltd: source a CFO"}
    if value is not None:
        body["client_value"] = value
    if deadline is not None:
        body["client_deadline_at"] = deadline
    started = await client.post(INSTANCES, json=body, headers=(starter or w.chidi.h))
    assert started.status_code == 200, started.text
    return started.json()


async def _make_first_task_overdue(db_session, instance_id: str) -> None:
    await db_session.execute(
        update(Task)
        .where(Task.workflow_instance_id == instance_id)
        .values(due_at=datetime.now(UTC) - timedelta(days=2))
    )


@pytest.mark.asyncio
async def test_a_case_keeps_its_figure_and_deadline_and_starts_on_track(client, monkeypatch):
    """The figure and deadline come back on the case, and nothing is late yet."""
    w = await _world(client, monkeypatch, "cv1")

    case = await _case(client, w, deadline=_later())

    assert float(case["client_value"]) == 2000000
    assert case["client_deadline_at"] is not None
    assert (case["value_status"], float(case["value_at_risk"]), float(case["value_lost"])) == ("on_track", 0, 0)


@pytest.mark.asyncio
async def test_a_case_without_a_figure_shows_no_money_state(client, monkeypatch):
    """Old and plain cases are unaffected."""
    w = await _world(client, monkeypatch, "cv2")

    case = await _case(client, w, value=None)

    assert case["client_value"] is None and case["value_status"] == "none"


@pytest.mark.asyncio
async def test_a_negative_figure_or_a_past_deadline_is_refused(client, monkeypatch):
    """422 for a figure below zero; the final deadline must be in the future."""
    w = await _world(client, monkeypatch, "cv3")
    template = await _template(client, w, ("Shortlist candidates", w.dispatch, {}))
    base = {"template_id": template["id"], "subject": "Zenith"}

    negative = await client.post(INSTANCES, json={**base, "client_value": "-5"}, headers=w.chidi.h)
    past = await client.post(
        INSTANCES, json={**base, "client_value": FEE, "client_deadline_at": _later(-1)}, headers=w.chidi.h
    )

    assert negative.status_code == 422
    assert past.status_code == 422


@pytest.mark.asyncio
async def test_a_late_task_puts_the_figure_at_risk_once(client, db_session, monkeypatch):
    """The first task is overdue: the case shows N2,000,000 at risk, on the case, the list and the summary."""
    w = await _world(client, monkeypatch, "cv4")
    case = await _case(client, w, deadline=_later())
    await _make_first_task_overdue(db_session, case["id"])

    detail = (await client.get(f"{INSTANCES}/{case['id']}", headers=w.hr)).json()
    listed = (await client.get(INSTANCES, headers=w.hr)).json()["data"][0]
    summary = (await client.get(SUMMARY, headers=w.hr)).json()

    assert (detail["value_status"], float(detail["value_at_risk"])) == ("at_risk", 2000000)
    assert listed["value_status"] == "at_risk"
    assert (float(summary["at_risk_total"]), summary["cases_at_risk"], float(summary["lost_total"])) == (2000000, 1, 0)
    assert summary["cases"][0]["subject"] == "Zenith Ltd: source a CFO"
    assert [t["title"].startswith("Shortlist candidates") for t in summary["cases"][0]["overdue_tasks"]] == [True]


@pytest.mark.asyncio
async def test_cancelling_the_case_loses_the_figure(client, monkeypatch):
    """Cancelled: nothing is at risk any more; the whole figure is lost."""
    w = await _world(client, monkeypatch, "cv5")
    case = await _case(client, w, deadline=_later())

    cancelled = await client.post(f"{INSTANCES}/{case['id']}/cancel", json={"reason": "Client withdrew"}, headers=w.hr)
    summary = (await client.get(SUMMARY, headers=w.hr)).json()

    assert cancelled.json()["value_status"] == "lost"
    assert (float(summary["lost_total"]), float(summary["at_risk_total"]), summary["cases_lost"]) == (2000000, 0, 1)


@pytest.mark.asyncio
async def test_missing_the_clients_deadline_loses_the_figure(client, db_session, monkeypatch):
    """The final deadline passes with the case unfinished: lost, even though no task is late."""
    w = await _world(client, monkeypatch, "cv6")
    case = await _case(client, w, deadline=_later())
    await db_session.execute(
        update(WorkflowInstance)
        .where(WorkflowInstance.id == case["id"])
        .values(client_deadline_at=datetime.now(UTC) - timedelta(hours=1))
    )

    detail = (await client.get(f"{INSTANCES}/{case['id']}", headers=w.hr)).json()

    assert (detail["value_status"], float(detail["value_lost"])) == ("lost", 2000000)


@pytest.mark.asyncio
async def test_without_a_deadline_the_figure_can_be_at_risk_but_is_counted_as_having_no_deadline(
    client, db_session, monkeypatch
):
    """No final deadline: at risk while late, and the summary says how many cases have none."""
    w = await _world(client, monkeypatch, "cv7")
    case = await _case(client, w, deadline=None)
    await _make_first_task_overdue(db_session, case["id"])

    summary = (await client.get(SUMMARY, headers=w.hr)).json()

    assert (float(summary["at_risk_total"]), summary["cases_without_deadline"]) == (2000000, 1)


@pytest.mark.asyncio
async def test_a_person_only_sees_the_figures_of_cases_they_may_see(client, monkeypatch):
    """HR sees the figure; Bola, who is not in the case, sees nothing."""
    w = await _world(client, monkeypatch, "cv8")
    await _case(client, w, deadline=_later())

    hr_view = (await client.get(SUMMARY, headers=w.hr)).json()
    outsider = (await client.get(SUMMARY, headers=w.bola.h)).json()

    assert float(hr_view["on_track_total"]) == 2000000
    assert (float(outsider["on_track_total"]), outsider["cases"]) == (0, [])
