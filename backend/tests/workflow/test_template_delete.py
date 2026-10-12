"""Tests for DELETE /workflow-templates/{id} (M11 slice B, endpoint 5).

"Start a case" does not exist until slice C, so the running cases here are
inserted straight into the table.
"""
import uuid
from datetime import UTC, datetime

import pytest

from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create, _names
from tests.workflow.test_workflow_tables import _instance


async def _add_case(db_session, world, template_id: str, **changes) -> None:
    """Put a case straight into the table (default: running) on the given template."""
    org_id = world.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    db_session.add(_instance(org_id, uuid.UUID(template_id), **changes))
    await db_session.flush()


@pytest.mark.asyncio
async def test_a_template_with_no_running_case_is_deleted_and_disappears(client, monkeypatch):
    """After the delete it is gone from the list and the direct read, and the audit log says who did it."""
    w = await _world(client, monkeypatch, "td1")
    template = await _create(client, w.hr, "Old Process", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    deleted = await client.delete(url, headers=w.hr)

    assert deleted.status_code == 200 and deleted.json()["id"] == template["id"]
    assert _names(await client.get(TEMPLATES, params={"include_archived": True}, headers=w.hr)) == []
    assert (await client.get(url, headers=w.hr)).status_code == 404
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_template", "entity_id": template["id"]}, headers=w.hr
    )
    entry = next(e for e in audit.json()["data"] if e["action"] == "delete")
    assert entry["actor_user_id"] == w.owner["user"]["id"]
    assert entry["changes"]["old"]["deleted_at"] is None and entry["changes"]["new"]["deleted_at"] is not None


@pytest.mark.asyncio
async def test_a_template_with_a_running_case_cannot_be_deleted(client, monkeypatch, db_session):
    """Two cases in progress: a 409 that names the count and points to archiving; nothing is deleted."""
    w = await _world(client, monkeypatch, "td2")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _add_case(db_session, w, template["id"], subject="Zenith Ltd")
    await _add_case(db_session, w, template["id"], subject="Acme Ltd")

    refused = await client.delete(f"{TEMPLATES}/{template['id']}", headers=w.hr)

    assert refused.status_code == 409 and refused.json()["code"] == "RESOURCE_IN_USE"
    assert "2 case(s)" in refused.json()["message"] and "Archive" in refused.json()["message"]
    assert _names(await client.get(TEMPLATES, headers=w.hr)) == ["Client Onboarding"]


@pytest.mark.asyncio
async def test_finished_and_cancelled_cases_do_not_block_a_delete(client, monkeypatch, db_session):
    """Only in-progress cases count; history does not."""
    w = await _world(client, monkeypatch, "td3")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _add_case(db_session, w, template["id"], status="completed", completed_at=datetime.now(UTC))
    await _add_case(db_session, w, template["id"], status="cancelled", cancel_reason="Client withdrew")

    deleted = await client.delete(f"{TEMPLATES}/{template['id']}", headers=w.hr)

    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_only_hr_and_managers_delete_and_the_template_must_exist(client, monkeypatch):
    """An employee gets a 403 and the template survives; an unknown or already deleted one is a 404."""
    w = await _world(client, monkeypatch, "td4")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    by_employee = await client.delete(url, headers=w.chidi.h)
    by_manager = await client.delete(url, headers=w.sam.h)
    again = await client.delete(url, headers=w.hr)
    unknown = await client.delete(f"{TEMPLATES}/00000000-0000-0000-0000-000000000000", headers=w.hr)

    assert by_employee.status_code == 403
    assert by_manager.status_code == 200
    assert again.status_code == 404 and unknown.status_code == 404
