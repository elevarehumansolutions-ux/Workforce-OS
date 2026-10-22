"""Tests for the nightly job's cross-tenant lookup of organizations (M12 slice D)."""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.modules.kpis.models import KPI
from app.modules.scoring.repository import ScoringRepository
from app.modules.tasks.models import Task
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import KPIS, _world


@pytest.mark.asyncio
async def test_only_organizations_with_a_kpi_or_a_deadline_task_are_returned(client, monkeypatch, db_session):
    """A has a KPI, B has a task with a deadline, C has neither (C only has departments), D has an undated task."""
    a = await _world(client, monkeypatch, "sl1")
    b = await _world(client, monkeypatch, "sl2")
    c = await _world(client, monkeypatch, "sl3")
    d = await _world(client, monkeypatch, "sl4")
    created = await client.post(KPIS, json={"department_id": a.dispatch, "name": "Deals", "weight": 50}, headers=a.hr)
    assert created.status_code == 200
    for world, due in ((b, datetime(2026, 8, 1, tzinfo=UTC)), (d, None)):
        await set_org_context(db_session, world.owner["organization"]["id"])
        db_session.add(
            Task(
                organization_id=uuid.UUID(world.owner["organization"]["id"]),
                department_id=uuid.UUID(world.dispatch),
                title="A task",
                due_at=due,
            )
        )
        await db_session.flush()

    # No company is selected: the lookup must still see across companies.
    await set_org_context(db_session, "")
    found = set(await ScoringRepository(db_session).list_organizations_needing_scoring())

    ids = {name: uuid.UUID(w.owner["organization"]["id"]) for name, w in (("a", a), ("b", b), ("c", c), ("d", d))}
    assert ids["a"] in found and ids["b"] in found
    assert ids["c"] not in found and ids["d"] not in found


@pytest.mark.asyncio
async def test_a_deleted_kpi_alone_does_not_make_an_organization_a_candidate(client, monkeypatch, db_session):
    """Once the only KPI is deleted, the organization is no longer on the list."""
    w = await _world(client, monkeypatch, "sl5")
    kpi = await client.post(KPIS, json={"department_id": w.dispatch, "name": "Deals", "weight": 50}, headers=w.hr)
    assert kpi.status_code == 200
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(
        update(KPI).where(KPI.id == uuid.UUID(kpi.json()["id"])).values(deleted_at=datetime.now(UTC))
    )

    await set_org_context(db_session, "")
    found = set(await ScoringRepository(db_session).list_organizations_needing_scoring())

    assert uuid.UUID(w.owner["organization"]["id"]) not in found
