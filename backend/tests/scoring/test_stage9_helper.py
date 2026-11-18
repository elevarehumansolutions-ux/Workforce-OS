"""Test for the Stage 9 test helper's ``unfreeze`` command (scripts/admin/stage9_time_helper.py).

The database refuses any change to a frozen row, including clearing its mark, and only the table
OWNER may switch that lock off. The app (and the helper, which runs inside the api container) uses
the restricted ``elevare_app`` role, so it cannot unfreeze. The first version of the command tried
and failed on its first live use (2026-11-18). Now ``unfreeze`` only PRINTS the SQL for the
database owner to run; this test checks that it prints the right SQL and changes nothing.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.modules.tenancy_identity.models import Organization
from tests.conftest import set_org_context
from tests.scoring.test_employee_scores import _done, _task, _two_kpis, at
from tests.scoring.test_nightly_job import JUST_AFTER_Q3, Q3_FIRST_DAY, _department, _night, _old_company
from tests.tasks.test_tasks_router import _world


def _load_helper():
    """Import the helper script (it is a script, not part of the app package)."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "admin" / "stage9_time_helper.py"
    spec = importlib.util.spec_from_file_location("stage9_time_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_unfreeze_prints_the_owner_sql_for_this_company_and_changes_nothing(
    client, monkeypatch, db_session, capsys
):
    """The SQL names the company, the quarter and all three tables, wraps each in switch-off/on, and no row changes."""
    w = await _world(client, monkeypatch, "uf1")
    lead_follow_up, _ = await _two_kpis(client, w)
    await _old_company(db_session, w)
    db_session.add(_task(w, "on time", lead_follow_up, w.chidi.employee_id, **_done(at(8, 1), at(7, 30))))
    await db_session.flush()
    await _night(db_session, w, JUST_AFTER_Q3)
    before = await _department(db_session, w.dispatch, Q3_FIRST_DAY)
    assert before.finalized_at is not None

    org_id = uuid.UUID(w.owner["organization"]["id"])
    await set_org_context(db_session, str(org_id))
    organization = (await db_session.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    await _load_helper().unfreeze(db_session, organization, Q3_FIRST_DAY)
    printed = capsys.readouterr().out
    after = await _department(db_session, w.dispatch, Q3_FIRST_DAY)

    assert str(org_id) in printed and str(Q3_FIRST_DAY) in printed
    for table in ("employee_kpi_scores", "department_scores", "executive_summaries"):
        assert f"ALTER TABLE {table} DISABLE TRIGGER freeze_finalized_rows;" in printed
        assert f"ALTER TABLE {table} ENABLE TRIGGER freeze_finalized_rows;" in printed
        assert f"UPDATE {table} SET finalized_at = NULL" in printed
    assert printed.index("BEGIN;") < printed.index("COMMIT;")
    assert after.finalized_at == before.finalized_at  # the helper itself changed nothing
