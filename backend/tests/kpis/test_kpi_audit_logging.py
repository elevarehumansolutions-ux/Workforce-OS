"""Every KPI mutation writes an audit entry.

The gap flagged in 08_DECISIONS.md/09_PROGRESS.md, closed here. Scenario:
Adaeze creates a KPI, edits it, records a score for it, and later
removes it via the group reconcile — each of those four actions must
leave its own trace in audit_log.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from tests.conftest import register_verified_and_login
from app.modules.audit_and_notification.models import AuditLog

KPIS = "/api/v1/kpis"
DEPARTMENTS = "/api/v1/departments"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def _audit_entries(db_session, entity_type, entity_id):
    rows = await db_session.scalars(
        select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
    )
    return list(rows)


@pytest.mark.asyncio
async def test_create_kpi_writes_an_audit_entry(client, db_session):
    """Creating a KPI logs a 'create' entry with the new fields as 'new'."""
    owner = await register_verified_and_login(client, email="kpi_audit1@example.com")
    h = _h(owner["access_token"])
    dept_id = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)).json()["id"]

    created = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 30}, headers=h
    )
    kpi_id = uuid.UUID(created.json()["id"])

    (entry,) = await _audit_entries(db_session, "kpi", kpi_id)
    assert entry.action == "create"
    assert entry.changes["old"] is None
    assert entry.changes["new"]["name"] == "Deals closed"


@pytest.mark.asyncio
async def test_update_kpi_writes_an_audit_entry_with_old_and_new(client, db_session):
    """Editing a KPI logs an 'update' entry with both the old and new weight."""
    owner = await register_verified_and_login(client, email="kpi_audit2@example.com")
    h = _h(owner["access_token"])
    dept_id = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)).json()["id"]
    created = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 30}, headers=h
    )
    kpi_id = uuid.UUID(created.json()["id"])

    await client.patch(f"{KPIS}/{kpi_id}", json={"weight": 40}, headers=h)

    entries = await _audit_entries(db_session, "kpi", kpi_id)
    (update_entry,) = [e for e in entries if e.action == "update"]
    assert update_entry.changes["old"]["weight"] == 30.0
    assert update_entry.changes["new"]["weight"] == 40.0


@pytest.mark.asyncio
async def test_reconcile_writes_create_update_and_delete_entries(client, db_session):
    """The group reconcile logs one entry per KPI it touches, not one for the batch."""
    owner = await register_verified_and_login(client, email="kpi_audit3@example.com")
    h = _h(owner["access_token"])
    dept_id = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)).json()["id"]
    a = await client.post(KPIS, json={"department_id": dept_id, "name": "A", "weight": 30}, headers=h)
    b = await client.post(KPIS, json={"department_id": dept_id, "name": "B", "weight": 70}, headers=h)
    a_id, b_id = uuid.UUID(a.json()["id"]), uuid.UUID(b.json()["id"])

    resp = await client.put(
        f"{DEPARTMENTS}/{dept_id}/kpis",
        json={"kpis": [{"id": str(a_id), "name": "A", "weight": 40}, {"name": "C", "weight": 60}]},
        headers=h,
    )
    c_id = uuid.UUID(next(k["id"] for k in resp.json()["kpis"] if k["name"] == "C"))

    a_entries = await _audit_entries(db_session, "kpi", a_id)
    assert any(e.action == "update" for e in a_entries)
    b_entries = await _audit_entries(db_session, "kpi", b_id)
    assert any(e.action == "delete" for e in b_entries)
    c_entries = await _audit_entries(db_session, "kpi", c_id)
    assert any(e.action == "create" for e in c_entries)


@pytest.mark.asyncio
async def test_score_upsert_writes_create_then_update_entries(client, db_session):
    """The first score call logs 'create'; a second call for the same period logs 'update'."""
    owner = await register_verified_and_login(client, email="kpi_audit4@example.com")
    h = _h(owner["access_token"])
    dept_id = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)).json()["id"]
    kpi = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 100, "target_value": 20},
        headers=h,
    )
    kpi_id = uuid.UUID(kpi.json()["id"])
    today = date.today()
    period = {
        "period_start": str(today - timedelta(days=10)),
        "period_end": str(today + timedelta(days=10)),
    }

    first = await client.post(f"{KPIS}/{kpi_id}/scores", json={**period, "actual_value": 8}, headers=h)
    await client.post(f"{KPIS}/{kpi_id}/scores", json={**period, "actual_value": 14}, headers=h)
    score_id = uuid.UUID(first.json()["id"])

    entries = await _audit_entries(db_session, "kpi_score", score_id)
    actions = sorted(e.action for e in entries)
    assert actions == ["create", "update"]
