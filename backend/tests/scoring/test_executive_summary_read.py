"""HTTP-level tests for reading the executive summary (M12 slice G)."""
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.scoring.models import ExecutiveSummary
from tests.conftest import set_org_context
from tests.scoring.test_department_performance import Q3 as Q3_PARAMS
from tests.tasks.test_tasks_router import _member, _world

URL = "/api/v1/company-performance-summary/executive-summary"


async def _save(db_session, w, text: str, source="ai", frozen=False) -> None:
    """A saved Q3 summary."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    db_session.add(ExecutiveSummary(
        organization_id=uuid.UUID(w.owner["organization"]["id"]),
        period_start=datetime(2026, 7, 1).date(),
        period_end=datetime(2026, 9, 30).date(),
        summary_text=text,
        source=source,
        facts_fingerprint="x" * 64,
        generated_at=datetime(2026, 9, 14, 3, 0, tzinfo=UTC),
        finalized_at=datetime(2026, 10, 5, tzinfo=UTC) if frozen else None,
    ))
    await db_session.flush()


@pytest.mark.asyncio
async def test_hr_reads_the_saved_summary_and_whether_it_is_final(client, monkeypatch, db_session):
    """The text, how it was written, when, and 'so far' versus final."""
    w = await _world(client, monkeypatch, "es1")
    await _save(db_session, w, "Sales is at 70, down 5.")

    so_far = (await client.get(URL, params=Q3_PARAMS, headers=w.hr)).json()
    assert (so_far["summary_text"], so_far["source"], so_far["is_final"]) == ("Sales is at 70, down 5.", "ai", False)
    assert so_far["no_data_reason"] is None and so_far["generated_at"].startswith("2026-09-14")

    w2 = await _world(client, monkeypatch, "es1b")
    await _save(db_session, w2, "Plain facts.", source="plain", frozen=True)
    final = (await client.get(URL, params=Q3_PARAMS, headers=w2.hr)).json()
    assert (final["source"], final["is_final"]) == ("plain", True)


@pytest.mark.asyncio
async def test_with_no_summary_yet_it_says_not_enough_data_instead_of_an_empty_box(client, monkeypatch, db_session):
    """No row: null text, a reason that names the 10-task bar, still a 200."""
    w = await _world(client, monkeypatch, "es2")

    resp = await client.get(URL, params=Q3_PARAMS, headers=w.hr)

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary_text"] is None and body["source"] is None and body["is_final"] is False
    assert body["no_data_reason"].startswith("Not enough data yet to write a summary") and "10" in body["no_data_reason"]


@pytest.mark.asyncio
async def test_only_hr_and_executives_may_read_it(client, monkeypatch, db_session):
    """An executive can; a head, a manager and an employee get the same 404."""
    w = await _world(client, monkeypatch, "es3")
    await _save(db_session, w, "Sales is at 70.")
    positions = (await client.get("/api/v1/positions", headers=w.hr)).json()["data"]
    executive = await _member(client, monkeypatch, w.hr, "tk_exec_es3@example.com", "business_executive",
                              positions[0]["id"], "Eve")

    assert (await client.get(URL, params=Q3_PARAMS, headers=executive.h)).status_code == 200
    bodies = []
    for refused in (w.tunde.h, w.dana.h, w.chidi.h):
        resp = await client.get(URL, params=Q3_PARAMS, headers=refused)
        assert resp.status_code == 404
        bodies.append(resp.json())
    assert bodies[0] == bodies[1] == bodies[2]


@pytest.mark.asyncio
async def test_another_companys_summary_is_never_shown(client, monkeypatch, db_session):
    """Company B's HR asks for Q3 and does not see company A's text."""
    a = await _world(client, monkeypatch, "es4")
    b = await _world(client, monkeypatch, "es4b")
    await _save(db_session, a, "Company A secret.")

    body = (await client.get(URL, params=Q3_PARAMS, headers=b.hr)).json()

    assert body["summary_text"] is None
