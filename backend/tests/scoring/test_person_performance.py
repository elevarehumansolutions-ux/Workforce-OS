"""HTTP-level tests for a person's performance card (M12 slice E).

Chidi's Q3 comes from the design example: on Lead Follow-up (weight 70) he had
3 tasks on time, 2 late and 1 never done, so 66.67. Contract Paperwork
(weight 30) had no tasks for him.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.modules.kpis.models import KPI
from tests.conftest import set_org_context
from app.modules.scoring.service import ScoringService
from tests.scoring.test_employee_scores import Q3_START, Q4_START, _chidis_quarter, _compute_q3, _two_kpis
from tests.tasks.test_tasks_router import _world

ME = "/api/v1/employees/me/performance"
Q3 = {"period_start": "2026-07-01", "period_end": "2026-09-30"}


def person_url(employee_id: str) -> str:
    """The by-id route for a person's card."""
    return f"/api/v1/employees/{employee_id}/performance"


async def _chidis_saved_quarter(client, db_session, w) -> tuple[str, str]:
    """Create both KPIs (dated before Q3 so they count for it), mark Chidi's Q3 and save it."""
    lead_follow_up, paperwork = await _two_kpis(client, w)
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(update(KPI).values(created_at=datetime(2026, 6, 1, tzinfo=UTC)))
    await _chidis_quarter(db_session, w, lead_follow_up)
    await _compute_q3(db_session, w)
    return lead_follow_up, paperwork


@pytest.mark.asyncio
async def test_chidi_reads_his_own_card(client, monkeypatch, db_session):
    """Per-KPI results, the overall score from the saved rows, and "1 of 2 counted"."""
    w = await _world(client, monkeypatch, "pp1")
    lead_follow_up, paperwork = await _chidis_saved_quarter(client, db_session, w)

    resp = await client.get(ME, params=Q3, headers=w.chidi.h)

    assert resp.status_code == 200
    card = resp.json()
    assert card["employee_id"] == w.chidi.employee_id and card["employee_name"] == "Chidi Tester"
    assert card["department_id"] == w.dispatch
    assert (card["period_start"], card["period_end"]) == ("2026-07-01", "2026-09-30")
    assert Decimal(card["overall_score"]) == Decimal("66.67")  # only the KPI that has a score counts
    assert (card["kpis_counted"], card["kpis_expected"]) == (1, 2)
    assert card["no_data_reason"] is None
    assert card["is_final"] is False  # the quarter was saved as a running figure, not frozen

    first, second = card["kpis"]  # heaviest first
    assert first["kpi_id"] == lead_follow_up and Decimal(first["weight"]) == Decimal("70")
    assert Decimal(first["score_percentage"]) == Decimal("66.67")
    assert (first["tasks_on_time"], first["tasks_late"], first["tasks_not_done"]) == (3, 2, 1)
    assert second["kpi_id"] == paperwork and second["score_percentage"] is None  # no data, not 0
    assert (second["tasks_on_time"], second["tasks_late"], second["tasks_not_done"]) == (0, 0, 0)


@pytest.mark.asyncio
async def test_who_may_open_chidis_card_and_everyone_else_gets_not_found(client, monkeypatch, db_session):
    """HR, his head and a manager of his department see it; a colleague, another department's manager do not."""
    w = await _world(client, monkeypatch, "pp2")
    await _chidis_saved_quarter(client, db_session, w)
    url = person_url(w.chidi.employee_id)

    for allowed in (w.hr, w.tunde.h, w.dana.h, w.chidi.h):
        assert (await client.get(url, params=Q3, headers=allowed)).status_code == 200

    nobody = await client.get(person_url(str(uuid.uuid4())), params=Q3, headers=w.hr)
    for refused in (w.bola.h, w.sam.h):
        resp = await client.get(url, params=Q3, headers=refused)
        assert resp.status_code == 404
        # No hint that the person exists: the answer is the same as for a person who does not.
        assert resp.json() == nobody.json()
    assert nobody.status_code == 404


@pytest.mark.asyncio
async def test_another_company_cannot_open_the_card(client, monkeypatch, db_session):
    """Even HR of another company gets "not found" for Chidi's id."""
    w = await _world(client, monkeypatch, "pp3")
    other = await _world(client, monkeypatch, "pp3b")
    await _chidis_saved_quarter(client, db_session, w)

    resp = await client.get(person_url(w.chidi.employee_id), params=Q3, headers=other.hr)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_me_needs_an_employee_record_and_the_dates_must_make_sense(client, monkeypatch, db_session):
    """HR has no employee record, so "me" is 404; half a range or a backwards range is 422."""
    w = await _world(client, monkeypatch, "pp4")

    assert (await client.get(ME, headers=w.hr)).status_code == 404
    assert (await client.get(ME, params={"period_start": "2026-07-01"}, headers=w.chidi.h)).status_code == 422
    backwards = {"period_start": "2026-09-30", "period_end": "2026-07-01"}
    assert (await client.get(ME, params=backwards, headers=w.chidi.h)).status_code == 422


@pytest.mark.asyncio
async def test_no_tasks_means_no_data_with_a_reason_never_zero(client, monkeypatch, db_session):
    """Bola has no scored tasks: no overall score, 0 of 2 counted, each KPI "no data"."""
    w = await _world(client, monkeypatch, "pp5")
    await _chidis_saved_quarter(client, db_session, w)

    card = (await client.get(ME, params=Q3, headers=w.bola.h)).json()

    assert card["overall_score"] is None
    assert (card["kpis_counted"], card["kpis_expected"]) == (0, 2)
    assert "No tasks linked to a KPI" in card["no_data_reason"]
    assert [line["score_percentage"] for line in card["kpis"]] == [None, None]


@pytest.mark.asyncio
async def test_a_kpi_created_after_the_period_is_not_missing_data_for_it(client, monkeypatch, db_session):
    """Asked about Q1, before either KPI existed: no lines, and the reason says the department had none."""
    w = await _world(client, monkeypatch, "pp6")
    await _chidis_saved_quarter(client, db_session, w)  # the KPIs are dated June 2026

    card = (await client.get(ME, params={"period_start": "2026-01-01", "period_end": "2026-03-31"},
                             headers=w.chidi.h)).json()

    assert card["kpis"] == [] and card["overall_score"] is None
    assert (card["kpis_counted"], card["kpis_expected"]) == (0, 0)
    assert card["no_data_reason"] == "This person's department had no KPIs in this period."


@pytest.mark.asyncio
async def test_a_closed_quarter_is_final_and_keeps_the_weights_it_was_scored_with(client, monkeypatch, db_session):
    """After the freeze the card says is_final, and changing a KPI's weight later does not change it."""
    w = await _world(client, monkeypatch, "pp7")
    lead_follow_up, _ = await _chidis_saved_quarter(client, db_session, w)
    org_id = uuid.UUID(w.owner["organization"]["id"])
    await ScoringService(db_session).finalize_employee_scores(org_id, Q3_START, Q4_START, Q4_START)
    await db_session.execute(update(KPI).where(KPI.id == uuid.UUID(lead_follow_up)).values(weight=Decimal("10")))

    card = (await client.get(ME, params=Q3, headers=w.chidi.h)).json()

    assert card["is_final"] is True
    assert Decimal(card["kpis"][0]["weight"]) == Decimal("70")  # not the new 10
    assert Decimal(card["overall_score"]) == Decimal("66.67")
