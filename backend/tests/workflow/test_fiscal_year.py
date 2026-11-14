"""PUT /fiscal-year: HR changes the month the company's financial year starts in
(08_DECISIONS.md 2026-11-14).

Scenario: a company's financial year runs April to March. HR sets April; the quarters then run
April to June, July to September, and so on.
"""
import pytest
from sqlalchemy import text

from tests.conftest import commit_like_production, set_org_context
from tests.tasks.test_tasks_router import _world

FISCAL = "/api/v1/fiscal-year"


async def _company_of(client, headers) -> dict:
    """The company the token belongs to, as GET /auth/me shows it (a fresh sign-up has just one)."""
    me = await client.get("/api/v1/auth/me", headers=headers)
    return me.json()["memberships"][0]["organization"]


async def _month_seen_by_hr(client, headers) -> int:
    return (await _company_of(client, headers))["fiscal_year_start_month"]


@pytest.mark.asyncio
async def test_hr_changes_the_month(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "fy1")
    commit_like_production(db_session, monkeypatch)

    resp = await client.put(FISCAL, json={"fiscal_year_start_month": 4}, headers=w.hr)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"fiscal_year_start_month": 4}
    assert await _month_seen_by_hr(client, w.hr) == 4


@pytest.mark.asyncio
async def test_only_an_hr_administrator_may_change_it(client, monkeypatch):
    w = await _world(client, monkeypatch, "fy2")
    body = {"fiscal_year_start_month": 4}

    assert (await client.put(FISCAL, json=body, headers=w.dana.h)).status_code == 403  # a manager
    assert (await client.put(FISCAL, json=body, headers=w.chidi.h)).status_code == 403  # an employee
    assert await _month_seen_by_hr(client, w.hr) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("month", [0, 13, -1])
async def test_a_month_that_does_not_exist_is_refused(client, monkeypatch, month):
    w = await _world(client, monkeypatch, "fy3")

    resp = await client.put(FISCAL, json={"fiscal_year_start_month": month}, headers=w.hr)

    assert resp.status_code == 422
    assert await _month_seen_by_hr(client, w.hr) == 1


@pytest.mark.asyncio
async def test_saving_the_same_month_again_is_fine_and_writes_no_audit_entry(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "fy4")
    commit_like_production(db_session, monkeypatch)

    resp = await client.put(FISCAL, json={"fiscal_year_start_month": 1}, headers=w.hr)

    assert resp.status_code == 200 and resp.json() == {"fiscal_year_start_month": 1}
    company = await _company_of(client, w.hr)
    await set_org_context(db_session, company["id"])
    result = await db_session.execute(text("SELECT count(*) FROM audit_log WHERE entity_type = 'fiscal_year'"))
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_a_change_is_written_to_the_audit_log(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "fy5")
    commit_like_production(db_session, monkeypatch)

    await client.put(FISCAL, json={"fiscal_year_start_month": 7}, headers=w.hr)

    company = await _company_of(client, w.hr)
    await set_org_context(db_session, company["id"])
    result = await db_session.execute(text("SELECT changes FROM audit_log WHERE entity_type = 'fiscal_year'"))
    changes = result.scalar_one()
    assert changes["old"] == {"fiscal_year_start_month": 1}
    assert changes["new"] == {"fiscal_year_start_month": 7}


@pytest.mark.asyncio
async def test_the_quarter_follows_the_new_month():
    """April start: on 15 May the running quarter is April to June."""
    from datetime import UTC, datetime

    from app.modules.tasks.periods import current_fiscal_quarter

    start, end = current_fiscal_quarter(4, "Africa/Lagos", datetime(2026, 5, 15, 12, tzinfo=UTC))

    assert (start.month, start.day) == (4, 1)
    assert (end.month, end.day) in [(6, 30), (7, 1)]  # end is the last day or the start of the next quarter
