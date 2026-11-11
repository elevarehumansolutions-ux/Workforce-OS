"""Undo merge: a merge can be reversed exactly while everything it touched is still waiting.

Scenario: Adaeze merges Customer Support into Operations, looks at the plan, and changes her
mind. 'Undo merge' puts the plan back exactly as it was before. Once Operations has been added
for real, the merge is final.
"""
from decimal import Decimal, InvalidOperation

import pytest

from tests.blueprint.test_blueprint_flow import BLUEPRINT, DEPARTMENTS, _by_title
from tests.blueprint.test_reshape import _listed, _plan_for, _real_id


def _same(first, second) -> bool:
    """Equal values; numbers that only differ in how many zeros they show ("20.0" and "20.00") are equal."""
    if first == second:
        return True
    try:
        return Decimal(str(first)) == Decimal(str(second))
    except (InvalidOperation, ValueError):
        return False


def _differences(first: dict, second: dict) -> list:
    """Every (title, field, first value, second value) where two views of the plan differ."""
    found = []
    for title in sorted(set(first) | set(second)):
        if title not in first or title not in second:
            found.append((title, "(exists)", title in first, title in second))
            continue
        for field in first[title]:
            if not _same(first[title][field], second[title].get(field)):
                found.append((title, field, first[title][field], second[title].get(field)))
    return found


async def _merge(client, headers, source, target):
    return await client.post(
        f"{BLUEPRINT}/{source.id}/merge", json={"target_id": str(target.id)}, headers=headers
    )


@pytest.mark.asyncio
async def test_undoing_a_department_merge_puts_the_whole_plan_back_exactly(client, db_session, monkeypatch):
    """Roles, objectives, KPIs weights and both capital shares are what they were before the merge."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "um_dept1@example.com")
    support, operations = _by_title(items, "Customer Support"), _by_title(items, "Operations")
    before = await _listed(client, headers)
    merged = await _merge(client, headers, support, operations)
    assert merged.json()["can_undo_merge"] is True

    resp = await client.post(f"{BLUEPRINT}/{support.id}/undo-merge", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["kind"] == "department"
    assert resp.json()["can_undo_merge"] is False
    assert _differences(before, await _listed(client, headers)) == []


@pytest.mark.asyncio
async def test_undoing_a_role_merge_restores_the_reporting_lines_even_after_a_loop_was_cut(
    client, db_session, monkeypatch
):
    """Director merged into its own report (a loop is cut), then undone: the chart is as it was."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "um_pos1@example.com")
    director, dispatch = _by_title(items, "Operations Director"), _by_title(items, "Dispatch Manager")
    before = await _listed(client, headers)
    await _merge(client, headers, director, dispatch)
    assert (await _listed(client, headers))["Dispatch Manager"]["reports_to_ref"] is None

    resp = await client.post(f"{BLUEPRINT}/{director.id}/undo-merge", headers=headers)

    assert resp.status_code == 200
    assert _differences(before, await _listed(client, headers)) == []


@pytest.mark.asyncio
async def test_undoing_a_merge_into_an_added_department_gives_the_capital_back(client, db_session, monkeypatch):
    """Support merged into the real Operations, then undone: Operations falls back to 60%, Support waits."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "um_ex1@example.com")
    support = _by_title(items, "Customer Support")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/approve", headers=headers)
    operations_id = await _real_id(client, headers, DEPARTMENTS, "name", "Operations")
    before = await _listed(client, headers)
    await client.post(f"{BLUEPRINT}/{support.id}/merge", json={"existing_id": operations_id}, headers=headers)
    merged_share = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]["revenue_allocation_percentage"]
    assert float(merged_share) == 100.0

    resp = await client.post(f"{BLUEPRINT}/{support.id}/undo-merge", headers=headers)

    assert resp.status_code == 200
    assert _differences(before, await _listed(client, headers)) == []
    real = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]
    assert float(real["revenue_allocation_percentage"]) == 60.0


@pytest.mark.asyncio
async def test_a_merge_cannot_be_undone_once_the_target_was_added(client, db_session, monkeypatch):
    """Operations is real now and holds Support's things, so moving them back would change real rows."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "um_late1@example.com")
    support, operations = _by_title(items, "Customer Support"), _by_title(items, "Operations")
    await _merge(client, headers, support, operations)
    await client.post(f"{BLUEPRINT}/{operations.id}/approve", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{support.id}/undo-merge", headers=headers)

    assert resp.status_code == 422
    assert "already been added" in resp.json()["message"]
    assert (await _listed(client, headers))["Customer Support"]["kind"] == "folded"


@pytest.mark.asyncio
async def test_a_left_out_note_from_the_ai_has_no_merge_to_undo(client, db_session, monkeypatch):
    """Only notes made by a merge can be undone; the AI's own 'covered by' notes cannot."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "um_ai1@example.com")
    note = _by_title(items, "Fleet Admin")

    listed = (await _listed(client, headers))["Fleet Admin"]
    resp = await client.post(f"{BLUEPRINT}/{note.id}/undo-merge", headers=headers)

    assert listed["can_undo_merge"] is False
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_adding_a_merged_item_back_on_its_own_ends_the_undo(client, db_session, monkeypatch):
    """'Make it a separate department' already restores it as a bare item; a later undo has nothing to do."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "um_sep1@example.com")
    support, operations = _by_title(items, "Customer Support"), _by_title(items, "Operations")
    await _merge(client, headers, support, operations)
    await client.post(f"{BLUEPRINT}/{support.id}/add-separately", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{support.id}/undo-merge", headers=headers)

    assert resp.status_code == 422
