"""Tests for archiving and unarchiving templates (M11 slice B, endpoint 4)."""
import pytest

from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create, _names


@pytest.mark.asyncio
async def test_an_archived_template_leaves_the_list_but_can_still_be_opened(client, monkeypatch):
    """Archive hides it from the default list; include_archived and a direct read still find it."""
    w = await _world(client, monkeypatch, "ta1")
    keep = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    retire = await _create(client, w.hr, "Old Process", w.dispatch)

    archived = await client.post(f"{TEMPLATES}/{retire['id']}/archive", headers=w.hr)

    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    assert _names(await client.get(TEMPLATES, headers=w.chidi.h)) == ["Client Onboarding"]
    assert _names(await client.get(TEMPLATES, params={"include_archived": True}, headers=w.hr)) == [
        "Client Onboarding",
        "Old Process",
    ]
    assert (await client.get(f"{TEMPLATES}/{retire['id']}", headers=w.hr)).status_code == 200
    assert keep["archived_at"] is None


@pytest.mark.asyncio
async def test_unarchive_brings_it_back_and_both_actions_are_audited(client, monkeypatch):
    """Archive then unarchive returns it to the default list, leaving two audit entries."""
    w = await _world(client, monkeypatch, "ta2")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    await client.post(f"{url}/archive", headers=w.hr)
    restored = await client.post(f"{url}/unarchive", headers=w.hr)

    assert restored.status_code == 200 and restored.json()["archived_at"] is None
    assert _names(await client.get(TEMPLATES, headers=w.hr)) == ["Client Onboarding"]
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_template", "entity_id": template["id"]}, headers=w.hr
    )
    actions = sorted(e["action"] for e in audit.json()["data"])
    assert actions == ["archive", "create", "unarchive"]
    archive_entry = next(e for e in audit.json()["data"] if e["action"] == "archive")
    assert archive_entry["changes"]["old"]["archived_at"] is None
    assert archive_entry["changes"]["new"]["archived_at"] is not None


@pytest.mark.asyncio
async def test_archiving_twice_or_unarchiving_a_live_template_is_a_409(client, monkeypatch):
    """The second archive, and an unarchive of a template that is not archived, are refused by name."""
    w = await _world(client, monkeypatch, "ta3")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    not_archived = await client.post(f"{url}/unarchive", headers=w.hr)
    await client.post(f"{url}/archive", headers=w.hr)
    again = await client.post(f"{url}/archive", headers=w.hr)

    assert not_archived.status_code == 409 and not_archived.json()["code"] == "WORKFLOW_TEMPLATE_NOT_ARCHIVED"
    assert again.status_code == 409 and again.json()["code"] == "WORKFLOW_TEMPLATE_ALREADY_ARCHIVED"


@pytest.mark.asyncio
async def test_only_hr_and_managers_archive_and_the_template_must_exist(client, monkeypatch):
    """A manager can archive; an employee gets a 403; an unknown template is a 404."""
    w = await _world(client, monkeypatch, "ta4")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    url = f"{TEMPLATES}/{template['id']}"

    by_employee = await client.post(f"{url}/archive", headers=w.chidi.h)
    by_manager = await client.post(f"{url}/archive", headers=w.sam.h)
    employee_unarchive = await client.post(f"{url}/unarchive", headers=w.chidi.h)
    unknown = await client.post(f"{TEMPLATES}/00000000-0000-0000-0000-000000000000/archive", headers=w.hr)

    assert by_employee.status_code == 403 and employee_unarchive.status_code == 403
    assert by_manager.status_code == 200
    assert unknown.status_code == 404
