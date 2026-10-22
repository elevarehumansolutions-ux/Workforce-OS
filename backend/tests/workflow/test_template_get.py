"""Tests for GET /workflow-templates/{id} (M11 slice B, endpoint 3a)."""
import pytest

from tests.tasks.test_tasks_router import _world
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create


@pytest.mark.asyncio
async def test_any_member_reads_one_template(client, monkeypatch):
    """Chidi (employee) can open a template HR built."""
    w = await _world(client, monkeypatch, "tg1")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)

    response = await client.get(f"{TEMPLATES}/{template['id']}", headers=w.chidi.h)

    assert response.status_code == 200
    assert response.json() == template


@pytest.mark.asyncio
async def test_an_unknown_template_or_another_companys_is_a_404(client, monkeypatch):
    """No such id, or an id from another company, looks exactly the same: not found."""
    mine = await _world(client, monkeypatch, "tg2")
    other = await _world(client, monkeypatch, "tg3")
    theirs = await _create(client, other.hr, "Someone Else's Process", other.dispatch)

    unknown = await client.get(f"{TEMPLATES}/00000000-0000-0000-0000-000000000000", headers=mine.hr)
    someone_elses = await client.get(f"{TEMPLATES}/{theirs['id']}", headers=mine.hr)
    malformed = await client.get(f"{TEMPLATES}/not-an-id", headers=mine.hr)

    assert unknown.status_code == 404 and unknown.json()["code"] == "WORKFLOW_TEMPLATE_NOT_FOUND"
    assert someone_elses.status_code == 404
    assert malformed.status_code == 422
