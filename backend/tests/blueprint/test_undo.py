"""Undo on an 'Added' plan item.

Scenario: Adaeze presses 'Add all' on the logistics plan, then changes her mind about the
Operations department. She is warned what goes with it, then undoes it and everything goes back
to waiting, ready to be added again. If a person added a role to it by hand, Undo refuses and
changes nothing.
"""
import pytest

from tests.blueprint.test_blueprint_flow import (
    BLUEPRINT,
    DEPARTMENTS,
    KPIS,
    POSITIONS,
    _by_title,
    _generate,
)


async def _add_everything(client, headers):
    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["skipped"] == []


async def _statuses(client, headers):
    rows = (await client.get(f"{BLUEPRINT}?limit=100", headers=headers)).json()["data"]
    return {row["title"]: row["status"] for row in rows}


@pytest.mark.asyncio
async def test_the_warning_counts_everything_added_under_a_department(client, db_session, monkeypatch):
    """Operations has 2 roles, 1 objective, 2 key results and 2 KPIs under it."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo1@example.com")
    await _add_everything(client, headers)
    department = _by_title(items, "Operations")

    resp = await client.get(f"{BLUEPRINT}/{department.id}/undo-preview", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Operations"
    assert body["removes"] == {"position": 2, "objective": 1, "key_result": 2, "kpi": 2}
    assert body["total"] == 7


@pytest.mark.asyncio
async def test_undoing_a_department_removes_everything_under_it_and_puts_it_all_back(
    client, db_session, monkeypatch
):
    """Nothing real is left, every item waits again, and it can all be added a second time."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo2@example.com")
    await _add_everything(client, headers)
    department = _by_title(items, "Operations")

    resp = await client.post(f"{BLUEPRINT}/{department.id}/undo", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"undone": 8}
    assert (await client.get(DEPARTMENTS, headers=headers)).json()["data"] == []
    assert (await client.get(POSITIONS, headers=headers)).json()["data"] == []
    assert (await client.get(f"{KPIS}?limit=100", headers=headers)).json()["data"] == []
    assert set((await _statuses(client, headers)).values()) == {"pending"}

    await _add_everything(client, headers)
    assert len((await client.get(DEPARTMENTS, headers=headers)).json()["data"]) == 1


@pytest.mark.asyncio
async def test_undoing_a_lone_kpi_warns_of_nothing_and_removes_only_it(client, db_session, monkeypatch):
    """A KPI has nothing under it: the warning is empty and the rest stays added."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo3@example.com")
    await _add_everything(client, headers)
    kpi = _by_title(items, "Average transit time")

    preview = (await client.get(f"{BLUEPRINT}/{kpi.id}/undo-preview", headers=headers)).json()
    assert preview["removes"] == {}
    assert preview["total"] == 0

    assert (await client.post(f"{BLUEPRINT}/{kpi.id}/undo", headers=headers)).json() == {"undone": 1}
    names = [k["name"] for k in (await client.get(f"{KPIS}?limit=100", headers=headers)).json()["data"]]
    assert names == ["On-time delivery rate"]
    statuses = await _statuses(client, headers)
    assert statuses["Average transit time"] == "pending"
    assert statuses["Operations"] == "approved"


@pytest.mark.asyncio
async def test_undo_keeps_the_wording_the_owner_chose(client, db_session, monkeypatch):
    """A role renamed before it was added comes back with her wording, not the AI's."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo4@example.com")
    director = _by_title(items, "Operations Director")
    await client.post(
        f"{BLUEPRINT}/{director.id}/edit", json={"title": "Head of Operations"}, headers=headers
    )

    assert (await client.post(f"{BLUEPRINT}/{director.id}/undo", headers=headers)).status_code == 200

    statuses = await _statuses(client, headers)
    assert statuses["Head of Operations"] == "pending"
    assert "Operations Director" not in statuses


@pytest.mark.asyncio
async def test_undo_is_refused_when_a_role_was_added_by_hand_and_changes_nothing(
    client, db_session, monkeypatch
):
    """A hand-made role reports to the plan's director: the department cannot be undone."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo5@example.com")
    await _add_everything(client, headers)
    department = _by_title(items, "Operations")
    real_department = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]
    await client.post(
        POSITIONS, json={"title": "Night Supervisor", "department_id": real_department["id"]}, headers=headers
    )

    resp = await client.post(f"{BLUEPRINT}/{department.id}/undo", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "RESOURCE_IN_USE"
    assert "position" in resp.json()["message"]
    assert len((await client.get(DEPARTMENTS, headers=headers)).json()["data"]) == 1
    assert len((await client.get(POSITIONS, headers=headers)).json()["data"]) == 3
    assert (await _statuses(client, headers))["Operations"] == "approved"


@pytest.mark.asyncio
async def test_undo_is_refused_when_a_kpi_was_added_by_hand(client, db_session, monkeypatch):
    """The Organization module does not look at KPIs, so Undo does: it would leave one orphaned."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo6@example.com")
    await _add_everything(client, headers)
    department = _by_title(items, "Operations")
    real_department = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]
    # Free some room, then add a KPI by hand to the same department.
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Average transit time').id}/undo", headers=headers)
    await client.post(
        KPIS, json={"department_id": real_department["id"], "name": "Fuel cost", "weight": 20}, headers=headers
    )

    resp = await client.post(f"{BLUEPRINT}/{department.id}/undo", headers=headers)

    assert resp.status_code == 409
    assert "KPI" in resp.json()["message"]
    assert len((await client.get(DEPARTMENTS, headers=headers)).json()["data"]) == 1


@pytest.mark.asyncio
async def test_a_second_click_on_undo_is_refused_clearly(client, db_session, monkeypatch):
    """Once undone the item waits again, so a repeated click has nothing to undo."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo7@example.com")
    await _add_everything(client, headers)
    kpi = _by_title(items, "Average transit time")
    await client.post(f"{BLUEPRINT}/{kpi.id}/undo", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{kpi.id}/undo", headers=headers)

    assert resp.status_code == 422
    assert "nothing to undo" in resp.json()["message"]


@pytest.mark.asyncio
async def test_a_rename_or_waiting_item_cannot_be_undone(client, db_session, monkeypatch):
    """Only things that became a real row can be undone; a waiting item has nothing to undo."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_undo8@example.com")
    waiting = _by_title(items, "Operations")

    resp = await client.get(f"{BLUEPRINT}/{waiting.id}/undo-preview", headers=headers)

    assert resp.status_code == 422
