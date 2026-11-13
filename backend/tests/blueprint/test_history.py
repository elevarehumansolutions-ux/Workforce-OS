"""The change history of the plan review: Undo and Redo during onboarding.

Scenario: Adaeze reviews the logistics plan. She adds Operations, merges Customer Support into
it, skips things, then changes her mind. The history lists what she did, newest first; she can
take a change back (and bring it back), but never in a way that leaves the plan half-broken:
an older change is refused while something she did later depends on it.
"""
import pytest

from tests.blueprint.test_blueprint_flow import (
    BLUEPRINT,
    DEPARTMENTS,
    POSITIONS,
    _by_title,
    _generate,
)
from tests.blueprint.test_reshape import _listed, _plan_for

HISTORY = f"{BLUEPRINT}/history"


async def _history(client, headers):
    resp = await client.get(HISTORY, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _do(client, headers, item, action, **body):
    resp = await client.post(f"{BLUEPRINT}/{item.id}/{action}", json=body or None, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp


async def _department_names(client, headers):
    return sorted(d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"])


# ---------------------------------------------------------------- recording and labels

@pytest.mark.asyncio
async def test_every_review_change_is_listed_newest_first_in_plain_words(client, db_session, monkeypatch):
    """Add, skip and merge each leave one line saying what was acted on."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist1@example.com")

    await _do(client, headers, _by_title(items, "Driver Lead"), "reject")
    await _do(client, headers, _by_title(items, "Customer Support"), "merge", target_id=str(_by_title(items, "Operations").id))
    await _do(client, headers, _by_title(items, "Operations"), "approve")

    entries = await _history(client, headers)

    assert [e["label"] for e in entries] == [
        'Added department "Operations"',
        'Merged department "Customer Support" into "Operations"',
        'Skipped role "Driver Lead"',
    ]
    assert all(e["state"] == "done" for e in entries)


@pytest.mark.asyncio
async def test_a_change_that_changed_nothing_is_not_recorded(client, db_session, monkeypatch):
    """Adding everything when nothing waits leaves no empty line in the history."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist2@example.com")
    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)
    first = await _history(client, headers)

    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    assert len(await _history(client, headers)) == len(first) == 1


# ---------------------------------------------------------------- undo and redo of an add

@pytest.mark.asyncio
async def test_undoing_an_add_removes_the_real_department_and_redo_brings_it_back(client, db_session, monkeypatch):
    """Operations is added, undone (gone, waiting again), then redone (back)."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist3@example.com")
    await _do(client, headers, _by_title(items, "Operations"), "approve")
    entry = (await _history(client, headers))[0]
    assert entry["can_undo"] is True

    undone = await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)

    assert undone.status_code == 200
    assert await _department_names(client, headers) == []
    assert (await _listed(client, headers))["Operations"]["status"] == "pending"
    after_undo = undone.json()["data"][0]
    assert (after_undo["state"], after_undo["can_undo"], after_undo["can_redo"]) == ("undone", False, True)

    redone = await client.post(f"{HISTORY}/{entry['id']}/redo", headers=headers)

    assert redone.status_code == 200
    assert await _department_names(client, headers) == ["Operations"]
    assert (await _listed(client, headers))["Operations"]["status"] == "approved"
    assert redone.json()["data"][0]["state"] == "done"


# ---------------------------------------------------------------- merge

@pytest.mark.asyncio
async def test_undoing_a_merge_puts_the_shares_and_the_department_back_and_redo_merges_again(
    client, db_session, monkeypatch
):
    """Customer Support comes back as its own department with its 40%, then is merged away again."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist4@example.com")
    before = await _listed(client, headers)
    await _do(client, headers, _by_title(items, "Customer Support"), "merge", target_id=str(_by_title(items, "Operations").id))
    merged = await _listed(client, headers)
    assert float(merged["Operations"]["revenue_allocation_pct"]) == 100
    entry = (await _history(client, headers))[0]

    await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)

    restored = await _listed(client, headers)
    assert restored["Customer Support"]["kind"] == "department"
    assert float(restored["Operations"]["revenue_allocation_pct"]) == float(before["Operations"]["revenue_allocation_pct"])
    assert float(restored["Customer Support"]["revenue_allocation_pct"]) == float(before["Customer Support"]["revenue_allocation_pct"])

    await client.post(f"{HISTORY}/{entry['id']}/redo", headers=headers)

    again = await _listed(client, headers)
    assert again["Customer Support"]["kind"] == "folded"
    assert float(again["Operations"]["revenue_allocation_pct"]) == 100


# ---------------------------------------------------------------- skip

@pytest.mark.asyncio
async def test_undoing_a_skip_restores_what_was_skipped_with_it(client, db_session, monkeypatch):
    """Skipping Customer Support also skipped its role, objective and KPI; undo brings all of it back."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist5@example.com")
    await _do(client, headers, _by_title(items, "Customer Support"), "reject")
    rows = await _listed(client, headers)
    assert rows["Support Lead"]["status"] == "rejected"
    entry = (await _history(client, headers))[0]

    await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)

    rows = await _listed(client, headers)
    assert {rows[t]["status"] for t in ("Customer Support", "Support Lead", "Happy customers", "Answer speed")} == {"pending"}


# ---------------------------------------------------------------- the owner's own wording

@pytest.mark.asyncio
async def test_undoing_an_edit_puts_the_original_wording_back_and_redo_keeps_hers(client, db_session, monkeypatch):
    """A role added as 'Head of Operations' goes back to the plan's 'Operations Director', then returns as hers."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist6@example.com")
    director = _by_title(items, "Operations Director")
    await _do(client, headers, director, "edit", title="Head of Operations")
    entry = (await _history(client, headers))[0]
    assert entry["label"] == 'Added role "Head of Operations" (suggested as "Operations Director")'

    await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)

    rows = await _listed(client, headers)
    assert rows["Operations Director"]["status"] == "pending"  # the AI's wording, not hers
    assert "Head of Operations" not in rows
    assert (await client.get(POSITIONS, headers=headers)).json()["data"] == []

    await client.post(f"{HISTORY}/{entry['id']}/redo", headers=headers)

    positions = [p["title"] for p in (await client.get(POSITIONS, headers=headers)).json()["data"]]
    assert positions == ["Head of Operations"]


@pytest.mark.asyncio
async def test_undoing_an_edit_of_kpi_details_puts_the_old_weight_back(client, db_session, monkeypatch):
    """A target of 99 typed when adding a KPI is undone to the plan's 95, and redo applies 99 again."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist7@example.com")
    await _do(client, headers, _by_title(items, "Operations"), "approve")
    kpi = _by_title(items, "On-time rate")
    await _do(client, headers, kpi, "edit", title="On-time rate", kpi_target_value="99")
    entry = (await _history(client, headers))[0]

    await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)
    assert (await _listed(client, headers))["On-time rate"]["kpi_target_value"] is None

    await client.post(f"{HISTORY}/{entry['id']}/redo", headers=headers)
    assert float((await _listed(client, headers))["On-time rate"]["kpi_target_value"]) == 99


# ---------------------------------------------------------------- order: nothing half-broken

@pytest.mark.asyncio
async def test_an_older_change_is_refused_while_a_later_one_depends_on_it(client, db_session, monkeypatch):
    """Operations was added, then Dispatch Manager under it: undo Operations says undo the role first."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist8@example.com")
    await _do(client, headers, _by_title(items, "Operations"), "approve")
    await _do(client, headers, _by_title(items, "Dispatch Manager"), "approve")
    entries = await _history(client, headers)
    newer, older = entries[0], entries[1]
    assert (newer["can_undo"], older["can_undo"]) == (True, False)
    assert older["reason"] == 'Undo "Added role "Dispatch Manager"" first.'

    refused = await client.post(f"{HISTORY}/{older['id']}/undo", headers=headers)

    assert refused.status_code == 409
    assert refused.json()["code"] == "BLUEPRINT_HISTORY_BLOCKED"
    assert await _department_names(client, headers) == ["Operations"]  # nothing changed

    await client.post(f"{HISTORY}/{newer['id']}/undo", headers=headers)
    allowed = await client.post(f"{HISTORY}/{older['id']}/undo", headers=headers)
    assert allowed.status_code == 200
    assert await _department_names(client, headers) == []


@pytest.mark.asyncio
async def test_a_change_that_touched_other_things_can_be_undone_out_of_order(client, db_session, monkeypatch):
    """Skipping Driver Lead has nothing to do with adding Operations: either can be undone first."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist9@example.com")
    await _do(client, headers, _by_title(items, "Operations"), "approve")
    await _do(client, headers, _by_title(items, "Driver Lead"), "reject")
    entries = await _history(client, headers)
    assert [e["can_undo"] for e in entries] == [True, True]

    resp = await client.post(f"{HISTORY}/{entries[1]['id']}/undo", headers=headers)  # the older one: Operations

    assert resp.status_code == 200
    assert await _department_names(client, headers) == []
    assert (await _listed(client, headers))["Driver Lead"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_redo_comes_back_in_order_and_a_new_change_clears_it(client, db_session, monkeypatch):
    """Two changes undone: only the one undone last can be redone first; a new change forgets both."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist10@example.com")
    await _do(client, headers, _by_title(items, "Driver Lead"), "reject")
    await _do(client, headers, _by_title(items, "Fleet Admin"), "add-separately")
    second, first = await _history(client, headers)
    await client.post(f"{HISTORY}/{second['id']}/undo", headers=headers)
    await client.post(f"{HISTORY}/{first['id']}/undo", headers=headers)

    wrong_order = await client.post(f"{HISTORY}/{second['id']}/redo", headers=headers)
    assert wrong_order.status_code == 409
    assert wrong_order.json()["message"].startswith('Redo "Skipped role "Driver Lead""')
    assert (await client.post(f"{HISTORY}/{first['id']}/redo", headers=headers)).status_code == 200
    assert (await client.post(f"{HISTORY}/{second['id']}/redo", headers=headers)).status_code == 200

    await client.post(f"{HISTORY}/{second['id']}/undo", headers=headers)
    await _do(client, headers, _by_title(items, "Support Lead"), "reject")

    states = [e["state"] for e in await _history(client, headers)]
    assert "undone" not in states  # redo list cleared by the new change


@pytest.mark.asyncio
async def test_a_card_undo_makes_the_history_line_say_already_undone(client, db_session, monkeypatch):
    """Operations was added, then undone with the Undo button on its card: the line cannot be undone twice."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist11@example.com")
    operations = _by_title(items, "Operations")
    await _do(client, headers, operations, "approve")
    await client.post(f"{BLUEPRINT}/{operations.id}/undo", headers=headers)

    entry = (await _history(client, headers))[0]

    assert (entry["state"], entry["can_undo"]) == ("already_undone", False)
    assert (await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)).status_code == 409


# ---------------------------------------------------------------- real rows and renames

@pytest.mark.asyncio
async def test_undo_is_refused_when_a_person_holds_a_role_the_change_added(client, db_session, monkeypatch):
    """A role added by the plan is later given to hand-made data: the real delete rules still apply."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist12@example.com")
    await _do(client, headers, _by_title(items, "Operations"), "approve")
    department = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]
    # A role made by hand, reporting to nothing in the plan, but sitting in the department.
    made = await client.post(POSITIONS, json={"title": "Fleet Clerk", "department_id": department["id"]}, headers=headers)
    assert made.status_code in (200, 201), made.text
    entry = (await _history(client, headers))[0]

    refused = await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)

    assert refused.status_code == 409
    assert await _department_names(client, headers) == ["Operations"]
    assert (await _listed(client, headers))["Operations"]["status"] == "approved"


@pytest.mark.asyncio
async def test_undoing_a_rename_sets_the_real_name_back(client, db_session, monkeypatch):
    """'Hr' was renamed to 'Human Resources' by accepting the clean-up; undo makes it 'Hr' again."""
    from tests.blueprint.test_blueprint_flow import _fake_anthropic, _logistics_answer, _org_with_dna, _usage
    from app.modules.blueprint.generation import generate_blueprint
    from app.modules.blueprint.schemas import ProposedCleanup

    _, headers, org_id = await _org_with_dna(client, db_session, "bp_hist13@example.com")
    await client.post(DEPARTMENTS, json={"name": "Hr"}, headers=headers)
    rename = ProposedCleanup(target="ED1", action="rename", new_name="Human Resources", note="Standard name.")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_logistics_answer([rename]))
    items = await generate_blueprint(db_session, org_id)
    await _do(client, headers, _by_title(items, "Human Resources"), "approve")
    assert await _department_names(client, headers) == ["Human Resources"]
    entry = (await _history(client, headers))[0]
    assert entry["label"] == 'Renamed "Hr" to "Human Resources"'

    await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)
    assert await _department_names(client, headers) == ["Hr"]
    assert (await _listed(client, headers))["Human Resources"]["status"] == "pending"

    await client.post(f"{HISTORY}/{entry['id']}/redo", headers=headers)
    assert await _department_names(client, headers) == ["Human Resources"]


@pytest.mark.asyncio
async def test_undoing_add_everything_removes_all_of_it(client, db_session, monkeypatch):
    """One 'Add everything' is one line; undoing it leaves no real department, role or KPI."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist14@example.com")
    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)
    entry = (await _history(client, headers))[0]
    assert entry["label"].startswith("Added everything waiting")

    resp = await client.post(f"{HISTORY}/{entry['id']}/undo", headers=headers)

    assert resp.status_code == 200
    assert await _department_names(client, headers) == []
    assert (await client.get(POSITIONS, headers=headers)).json()["data"] == []
    assert {i["status"] for i in (await _listed(client, headers)).values()} == {"pending"}


# ---------------------------------------------------------------- limits and access

@pytest.mark.asyncio
async def test_only_the_last_twenty_changes_are_kept(client, db_session, monkeypatch):
    """With the limit lowered to 3, five changes leave the newest three (the cap is a constant, KEEP_LAST)."""
    import app.modules.blueprint.history as history_module

    monkeypatch.setattr(history_module, "KEEP_LAST", 3)
    headers, items = await _plan_for(client, db_session, monkeypatch, "bp_hist15@example.com")
    for title in ("Driver Lead", "Dispatch Manager", "Support Lead", "Operations Director", "On-time rate"):
        await _do(client, headers, _by_title(items, title), "reject")

    entries = await _history(client, headers)

    assert [e["label"] for e in entries] == [
        'Skipped KPI "On-time rate"',
        'Skipped role "Operations Director"',
        'Skipped role "Support Lead"',
    ]


@pytest.mark.asyncio
async def test_an_unknown_change_is_a_404_and_each_company_has_its_own_history(client, db_session, monkeypatch):
    """Another id finds nothing, and a second company never sees the first one's changes."""
    import uuid
    from tests.conftest import register_verified_and_login
    headers, _ = await _plan_for(client, db_session, monkeypatch, "bp_hist16@example.com")

    missing = await client.post(f"{HISTORY}/{uuid.uuid4()}/undo", headers=headers)
    assert missing.status_code == 404

    outsider = await register_verified_and_login(client, email="bp_hist16b@example.com")
    other_org = {"Authorization": f"Bearer {outsider['access_token']}"}
    own = await client.get(HISTORY, headers=other_org)
    assert own.status_code == 200 and own.json()["data"] == []  # their own (empty) history, not ours
