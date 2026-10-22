"""Tests for GET /workflow-templates/{id}/steps (M11 slice B, endpoint 6b)."""
import uuid
from datetime import UTC, datetime

import pytest

from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import _world
from tests.workflow.test_step_add import _add
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_list import _create
from tests.workflow.test_workflow_tables import _step


def _names_in_order(response) -> list[tuple[int, str]]:
    """The listed steps as (position, name) pairs."""
    return [(s["step_order"], s["name"]) for s in response.json()]


@pytest.mark.asyncio
async def test_any_member_sees_the_steps_in_order(client, monkeypatch):
    """Chidi (employee) reads the steps; one inserted in the middle comes back in its place."""
    w = await _world(client, monkeypatch, "sl1")
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _add(client, w.hr, template["id"], "Sales hand-off", w.sales, default_turnaround_hours=24)
    await _add(client, w.hr, template["id"], "Legal check", w.sales)
    await _add(client, w.hr, template["id"], "Finance review", w.dispatch, step_order=2)

    listed = await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.chidi.h)

    assert listed.status_code == 200
    assert _names_in_order(listed) == [(1, "Sales hand-off"), (2, "Finance review"), (3, "Legal check")]
    assert listed.json()[0]["default_turnaround_hours"] == 24
    assert listed.json()[0]["department_id"] == w.sales


@pytest.mark.asyncio
async def test_a_template_with_no_steps_gives_an_empty_list_and_an_unknown_one_a_404(client, monkeypatch):
    """No steps yet is a normal empty list; a missing or other-company template is a 404."""
    mine = await _world(client, monkeypatch, "sl2")
    other = await _world(client, monkeypatch, "sl3")
    empty = await _create(client, mine.hr, "Client Onboarding", mine.dispatch)
    theirs = await _create(client, other.hr, "Someone Else's", other.dispatch)

    no_steps = await client.get(f"{TEMPLATES}/{empty['id']}/steps", headers=mine.hr)
    unknown = await client.get(f"{TEMPLATES}/00000000-0000-0000-0000-000000000000/steps", headers=mine.hr)
    someone_elses = await client.get(f"{TEMPLATES}/{theirs['id']}/steps", headers=mine.hr)

    assert no_steps.status_code == 200 and no_steps.json() == []
    assert unknown.status_code == 404 and unknown.json()["code"] == "WORKFLOW_TEMPLATE_NOT_FOUND"
    assert someone_elses.status_code == 404


@pytest.mark.asyncio
async def test_deleted_steps_are_left_out_and_archived_templates_still_list(client, monkeypatch, db_session):
    """A soft-deleted step is not shown; an archived template's steps still are."""
    w = await _world(client, monkeypatch, "sl4")
    org_id = w.owner["organization"]["id"]
    template = await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _add(client, w.hr, template["id"], "Kept", w.sales)
    await set_org_context(db_session, org_id)
    db_session.add(
        _step(org_id, uuid.UUID(template["id"]), w.sales, name="Removed", step_order=2, deleted_at=datetime.now(UTC))
    )
    await db_session.flush()
    await client.post(f"{TEMPLATES}/{template['id']}/archive", headers=w.hr)

    listed = await client.get(f"{TEMPLATES}/{template['id']}/steps", headers=w.hr)

    assert _names_in_order(listed) == [(1, "Kept")]
