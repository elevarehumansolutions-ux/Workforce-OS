"""Tests for PUT /workflow-templates/{id}/steps/order (M11 slice B, endpoint 6e)."""
import pytest

from tests.tasks.test_tasks_router import AUDIT, _world
from tests.workflow.test_step_delete import _template_with_steps
from tests.workflow.test_template_create import TEMPLATES
from tests.workflow.test_template_delete import _add_case


def _ids(steps: list[dict], *names: str) -> list[str]:
    """The ids of the named steps, in the order the names are given."""
    by_name = {s["name"]: s["id"] for s in steps}
    return [by_name[name] for name in names]


async def _listed(client, w, template_id: str) -> list[tuple[int, str]]:
    """The template's steps as (position, name), read through the list endpoint."""
    response = await client.get(f"{TEMPLATES}/{template_id}/steps", headers=w.hr)
    return [(s["step_order"], s["name"]) for s in response.json()]


@pytest.mark.asyncio
async def test_hr_puts_the_steps_in_a_new_order_and_it_is_audited(client, monkeypatch):
    """Sales, Finance, Legal become Legal, Sales, Finance; the audit entry shows old and new."""
    w = await _world(client, monkeypatch, "so1")
    template, steps = await _template_with_steps(client, w, "Sales", "Finance", "Legal")
    new_order = _ids(steps, "Legal", "Sales", "Finance")

    reordered = await client.put(
        f"{TEMPLATES}/{template['id']}/steps/order", json={"step_ids": new_order}, headers=w.hr
    )

    assert reordered.status_code == 200
    assert [(s["step_order"], s["name"]) for s in reordered.json()] == [(1, "Legal"), (2, "Sales"), (3, "Finance")]
    assert await _listed(client, w, template["id"]) == [(1, "Legal"), (2, "Sales"), (3, "Finance")]
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_template", "entity_id": template["id"]}, headers=w.hr
    )
    entry = next(e for e in audit.json()["data"] if e["action"] == "reorder")
    assert entry["changes"]["old"]["step_ids"] == _ids(steps, "Sales", "Finance", "Legal")
    assert entry["changes"]["new"]["step_ids"] == new_order


@pytest.mark.asyncio
async def test_sending_the_current_order_changes_nothing_and_writes_no_audit_entry(client, monkeypatch):
    """A no-op reorder succeeds quietly."""
    w = await _world(client, monkeypatch, "so2")
    template, steps = await _template_with_steps(client, w, "Sales", "Finance")

    same = await client.put(
        f"{TEMPLATES}/{template['id']}/steps/order",
        json={"step_ids": _ids(steps, "Sales", "Finance")},
        headers=w.hr,
    )

    assert same.status_code == 200
    assert [s["name"] for s in same.json()] == ["Sales", "Finance"]
    audit = await client.get(
        AUDIT, params={"entity_type": "workflow_template", "entity_id": template["id"]}, headers=w.hr
    )
    assert [e["action"] for e in audit.json()["data"]] == ["create"]


@pytest.mark.asyncio
async def test_the_list_must_be_exactly_the_templates_steps(client, monkeypatch):
    """A missing step, an unknown id and a repeated id are each a 422; the order is unchanged."""
    w = await _world(client, monkeypatch, "so3")
    template, steps = await _template_with_steps(client, w, "Sales", "Finance", "Legal")
    other_template, other_steps = await _template_with_steps(client, w, "Elsewhere")
    url = f"{TEMPLATES}/{template['id']}/steps/order"

    missing = await client.put(url, json={"step_ids": _ids(steps, "Finance", "Sales")}, headers=w.hr)
    foreign = await client.put(
        url, json={"step_ids": _ids(steps, "Finance", "Sales") + [other_steps[0]["id"]]}, headers=w.hr
    )
    repeated = await client.put(url, json={"step_ids": _ids(steps, "Sales", "Sales", "Legal")}, headers=w.hr)
    malformed = await client.put(url, json={"step_ids": ["not-an-id"]}, headers=w.hr)

    assert missing.status_code == 422 and "3 step(s)" in missing.json()["message"]
    assert foreign.status_code == 422 and repeated.status_code == 422 and malformed.status_code == 422
    assert await _listed(client, w, template["id"]) == [(1, "Sales"), (2, "Finance"), (3, "Legal")]
    assert await _listed(client, w, other_template["id"]) == [(1, "Elsewhere")]


@pytest.mark.asyncio
async def test_reordering_is_refused_while_a_case_is_running(client, monkeypatch, db_session):
    """One running case blocks it with a 409; once the case is finished it works."""
    w = await _world(client, monkeypatch, "so4")
    template, steps = await _template_with_steps(client, w, "Sales", "Finance")
    await _add_case(db_session, w, template["id"], subject="Zenith Ltd")
    url = f"{TEMPLATES}/{template['id']}/steps/order"
    swapped = {"step_ids": _ids(steps, "Finance", "Sales")}

    refused = await client.put(url, json=swapped, headers=w.hr)

    assert refused.status_code == 409 and refused.json()["code"] == "RESOURCE_IN_USE"
    assert "1 case(s)" in refused.json()["message"]
    assert await _listed(client, w, template["id"]) == [(1, "Sales"), (2, "Finance")]


@pytest.mark.asyncio
async def test_finished_cases_do_not_block_and_only_builders_reorder(client, monkeypatch, db_session):
    """A completed case allows it; a manager may reorder; an employee gets a 403; unknown template is a 404."""
    from datetime import UTC, datetime

    w = await _world(client, monkeypatch, "so5")
    template, steps = await _template_with_steps(client, w, "Sales", "Finance")
    await _add_case(db_session, w, template["id"], status="completed", completed_at=datetime.now(UTC))
    url = f"{TEMPLATES}/{template['id']}/steps/order"
    swapped = {"step_ids": _ids(steps, "Finance", "Sales")}

    by_employee = await client.put(url, json=swapped, headers=w.chidi.h)
    by_manager = await client.put(url, json=swapped, headers=w.sam.h)
    unknown = await client.put(
        f"{TEMPLATES}/00000000-0000-0000-0000-000000000000/steps/order", json={"step_ids": []}, headers=w.hr
    )

    assert by_employee.status_code == 403
    assert by_manager.status_code == 200
    assert unknown.status_code == 404
    assert await _listed(client, w, template["id"]) == [(1, "Finance"), (2, "Sales")]
