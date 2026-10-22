"""The blueprint end to end: generate, review, apply (real API, Claude faked).

Scenario: Adaeze signs up as HR administrator of a logistics company and
saves her Business DNA. The AI proposes a structure; she reviews it.
"""
import uuid

import pytest
from sqlalchemy import func, select

from app.modules.ai.models import AIUsageLog
from app.modules.blueprint.generation import generate_blueprint
from app.modules.blueprint.models import BlueprintItem
from app.modules.blueprint.schemas import (
    BlueprintAnswer,
    ProposedCleanup,
    ProposedDepartment,
    ProposedObjective,
    ProposedPosition,
)
from app.modules.blueprint.tasks import run_blueprint_generation
from tests.ai.test_llm_generate_structured import _fake_anthropic, _usage
from tests.audit_and_notification.test_audit_log import _invite_and_accept
from tests.conftest import register_verified_and_login, set_org_context

BLUEPRINT = "/api/v1/blueprint"
DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
OKRS = "/api/v1/okrs"


def _auth(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


def _logistics_answer(extra_cleanups=()) -> BlueprintAnswer:
    """Operations (Director <- Manager), plus one company objective with two key results."""
    return BlueprintAnswer(
        departments=[ProposedDepartment(ref="D1", name="Operations", rationale="Moves the goods.")],
        positions=[
            ProposedPosition(ref="P1", title="Operations Director", department="D1", rationale="Leads."),
            ProposedPosition(
                ref="P2", title="Dispatch Manager", department="D1", reports_to="P1", rationale="Routes."
            ),
        ],
        objectives=[
            ProposedObjective(
                ref="O1", title="Deliver on time", department="D1",
                key_results=["95% on-time deliveries", "Cut average transit time to 2 days"],
                rationale="Customers value speed.",
            )
        ],
        cleanups=list(extra_cleanups),
    )


async def _org_with_dna(client, db_session, email, industry="Logistics"):
    """Register an org and save its Business DNA; return (login, headers, org_id)."""
    login = await register_verified_and_login(client, email=email)
    headers = _auth(login)
    await client.put(
        "/api/v1/business-dna",
        json={"industry": industry, "products_services_description": "Freight and last-mile delivery"},
        headers=headers,
    )
    org_id = uuid.UUID(login["organization"]["id"])
    await set_org_context(db_session, org_id)
    return login, headers, org_id


async def _generate(client, db_session, monkeypatch, email, answer=None):
    """Org with DNA and a saved blueprint; returns (login, headers, org_id, items)."""
    login, headers, org_id = await _org_with_dna(client, db_session, email)
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=answer or _logistics_answer())
    items = await generate_blueprint(db_session, org_id)
    return login, headers, org_id, items


def _by_title(items, title):
    return next(i for i in items if i.title == title)


# ------------------------------------------------------------------ generation

@pytest.mark.asyncio
async def test_generation_saves_pending_items_and_logs_the_cost(client, db_session, monkeypatch):
    """Nothing real is created: 1 department, 2 positions, 1 objective, 2 key results, all pending."""
    _, headers, org_id, items = await _generate(client, db_session, monkeypatch, "bp_gen1@example.com")

    assert sorted(i.kind for i in items) == [
        "department", "key_result", "key_result", "objective", "position", "position",
    ]
    assert {i.status for i in items} == {"pending"}
    assert (await client.get(DEPARTMENTS, headers=headers)).json()["data"] == []
    assert await db_session.scalar(select(func.count()).select_from(AIUsageLog)) == 1


@pytest.mark.asyncio
async def test_no_business_dna_means_no_ai_call(client, db_session, monkeypatch):
    """With nothing to design from, Claude is never asked."""
    login = await register_verified_and_login(client, email="bp_nodna@example.com")
    org_id = uuid.UUID(login["organization"]["id"])
    await set_org_context(db_session, org_id)
    seen = _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_logistics_answer())

    assert await generate_blueprint(db_session, org_id) == []
    assert seen == {}


@pytest.mark.asyncio
async def test_a_second_run_while_items_wait_does_nothing(client, db_session, monkeypatch):
    """Pending items are already waiting, so no second batch is piled on top."""
    _, _, org_id, items = await _generate(client, db_session, monkeypatch, "bp_gen2@example.com")

    assert await generate_blueprint(db_session, org_id) == []
    assert await db_session.scalar(select(func.count()).select_from(BlueprintItem)) == len(items)


@pytest.mark.asyncio
async def test_the_dna_save_job_runs_only_the_first_time(client, db_session, monkeypatch):
    """first_time_only: an organization that already had a blueprint is left alone."""
    _, _, org_id, _ = await _generate(client, db_session, monkeypatch, "bp_gen3@example.com")
    await db_session.execute(
        BlueprintItem.__table__.update().values(status="rejected")
    )

    assert await run_blueprint_generation(db_session, org_id, first_time_only=True) == 0


@pytest.mark.asyncio
async def test_saving_business_dna_asks_for_a_first_time_blueprint(client, monkeypatch):
    """PUT /business-dna enqueues generation with first_time_only=True."""
    calls = []

    async def fake_trigger(organization_id, *, first_time_only):
        calls.append((organization_id, first_time_only))

    import app.modules.business_dna.router as dna_router

    monkeypatch.setattr(dna_router, "trigger_blueprint_generation", fake_trigger)
    login = await register_verified_and_login(client, email="bp_dna@example.com")

    await client.put("/api/v1/business-dna", json={"industry": "Retail"}, headers=_auth(login))

    assert calls == [(uuid.UUID(login["organization"]["id"]), True)]


# ----------------------------------------------------------------- listing and gates

@pytest.mark.asyncio
async def test_hr_lists_the_pending_items(client, db_session, monkeypatch):
    """The review screen asks for status=pending and gets everything in the AI's order."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_list@example.com")

    resp = await client.get(f"{BLUEPRINT}?status=pending", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == len(items)
    assert resp.json()["data"][0]["kind"] == "department"


@pytest.mark.asyncio
async def test_an_employee_cannot_see_or_review_the_blueprint(client, db_session, monkeypatch):
    """Only HR administrators and business executives."""
    login, _, _, items = await _generate(client, db_session, monkeypatch, "bp_gate@example.com")
    employee = await _invite_and_accept(client, monkeypatch, login, "bp_gate_emp@example.com", "employee")
    h = _auth(employee)

    assert (await client.get(BLUEPRINT, headers=h)).status_code == 403
    assert (await client.post(f"{BLUEPRINT}/{items[0].id}/approve", headers=h)).status_code == 403
    assert (await client.post(f"{BLUEPRINT}/accept-all", headers=h)).status_code == 403
    assert (await client.post(f"{BLUEPRINT}/generate", headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_another_organizations_item_is_a_404(client, db_session, monkeypatch):
    """Row-level security: Kelechi cannot approve Adaeze's item."""
    _, _, _, items = await _generate(client, db_session, monkeypatch, "bp_iso_a@example.com")
    other = await register_verified_and_login(client, email="bp_iso_b@example.com")
    await set_org_context(db_session, uuid.UUID(other["organization"]["id"]))

    resp = await client.post(f"{BLUEPRINT}/{items[0].id}/approve", headers=_auth(other))

    assert resp.status_code == 404
    assert resp.json()["code"] == "BLUEPRINT_ITEM_NOT_FOUND"


@pytest.mark.asyncio
async def test_generate_endpoint_queues_unless_items_are_waiting(client, db_session, monkeypatch):
    """Nothing pending: queued. Something pending: already_pending, nothing queued."""
    calls = []

    async def fake_trigger(organization_id, *, first_time_only):
        calls.append(first_time_only)

    import app.modules.blueprint.router as blueprint_router

    monkeypatch.setattr(blueprint_router, "trigger_blueprint_generation", fake_trigger)
    login, headers, _ = await _org_with_dna(client, db_session, "bp_trig@example.com")

    first = await client.post(f"{BLUEPRINT}/generate", headers=headers)
    assert (first.status_code, first.json()["status"], calls) == (202, "queued", [False])

    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_logistics_answer())
    await generate_blueprint(db_session, uuid.UUID(login["organization"]["id"]))
    second = await client.post(f"{BLUEPRINT}/generate", headers=headers)
    assert (second.json()["status"], calls) == ("already_pending", [False])


# --------------------------------------------------------------------- reviewing

@pytest.mark.asyncio
async def test_approving_a_position_approves_its_department_and_boss_first(
    client, db_session, monkeypatch
):
    """Approve 'Dispatch Manager': Operations and the Director are created first, in the right chart."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_appr@example.com")
    manager = _by_title(items, "Dispatch Manager")

    resp = await client.post(f"{BLUEPRINT}/{manager.id}/approve", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    departments = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    assert [d["name"] for d in departments] == ["Operations"]
    positions = (await client.get(POSITIONS, headers=headers)).json()["data"]
    by_title = {p["title"]: p for p in positions}
    assert set(by_title) == {"Operations Director", "Dispatch Manager"}
    assert by_title["Dispatch Manager"]["reports_to_position_id"] == by_title["Operations Director"]["id"]
    assert by_title["Dispatch Manager"]["department_id"] == departments[0]["id"]
    assert by_title["Operations Director"]["reports_to_position_id"] is None


@pytest.mark.asyncio
async def test_approving_twice_is_a_409_and_an_unknown_id_a_404(client, db_session, monkeypatch):
    """The second reviewer loses cleanly."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_twice@example.com")
    department = _by_title(items, "Operations")

    assert (await client.post(f"{BLUEPRINT}/{department.id}/approve", headers=headers)).status_code == 200
    again = await client.post(f"{BLUEPRINT}/{department.id}/approve", headers=headers)
    assert (again.status_code, again.json()["code"]) == (409, "BLUEPRINT_ITEM_ALREADY_REVIEWED")
    assert (await client.post(f"{BLUEPRINT}/{uuid.uuid4()}/approve", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_a_child_of_a_rejected_department_cannot_be_approved(client, db_session, monkeypatch):
    """Adaeze rejects Operations, then tries its Director: refused with a clear reason."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_rej@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/reject", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations Director').id}/approve", headers=headers)

    assert (resp.status_code, resp.json()["code"]) == (409, "BLUEPRINT_PARENT_REJECTED")
    assert (await client.get(POSITIONS, headers=headers)).json()["data"] == []


@pytest.mark.asyncio
async def test_a_rejected_boss_only_leaves_a_gap_in_the_chart(client, db_session, monkeypatch):
    """The Director is rejected; the Manager is still created, just with nobody above."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_gap@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations Director').id}/reject", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Dispatch Manager').id}/approve", headers=headers)

    assert resp.status_code == 200
    positions = (await client.get(POSITIONS, headers=headers)).json()["data"]
    assert [(p["title"], p["reports_to_position_id"]) for p in positions] == [("Dispatch Manager", None)]


@pytest.mark.asyncio
async def test_edit_creates_the_real_row_with_hr_wording(client, db_session, monkeypatch):
    """Adaeze renames the proposed department before accepting it."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_edit@example.com")

    resp = await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/edit",
        json={"title": "Logistics Operations"},
        headers=headers,
    )

    assert (resp.status_code, resp.json()["status"]) == (200, "edited")
    names = [d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"]]
    assert names == ["Logistics Operations"]
    blank = await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Dispatch Manager').id}/edit", json={"title": ""}, headers=headers
    )
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_accept_all_builds_the_whole_structure_and_the_okrs(client, db_session, monkeypatch):
    """One click: department, the two-level chart, the objective with both key results."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_all@example.com")

    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"accepted": len(items), "skipped": []}
    positions = (await client.get(POSITIONS, headers=headers)).json()["data"]
    assert len(positions) == 2
    okrs = (await client.get(OKRS, headers=headers)).json()["data"]
    assert [o["title"] for o in okrs] == ["Deliver on time"]
    department_id = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]["id"]
    assert okrs[0]["department_id"] == department_id
    key_results = (await client.get(f"{OKRS}/{okrs[0]['id']}/key-results", headers=headers)).json()["data"]
    assert sorted(k["description"] for k in key_results) == [
        "95% on-time deliveries", "Cut average transit time to 2 days",
    ]
    assert (await client.get(f"{BLUEPRINT}?status=pending", headers=headers)).json()["data"] == []


@pytest.mark.asyncio
async def test_accept_all_skips_what_cannot_be_applied_and_keeps_the_rest(
    client, db_session, monkeypatch
):
    """Renaming 'Marketing' to 'Sales' clashes with the real 'Sales': skipped, reason given, the rest goes through."""
    login, headers, org_id = await _org_with_dna(client, db_session, "bp_skip@example.com")
    await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)
    marketing = (await client.post(DEPARTMENTS, json={"name": "Marketing"}, headers=headers)).json()
    # Labels follow (created_at, id), and inside one test transaction created_at is
    # identical for both rows, so find which label Marketing got.
    ids_in_label_order = sorted(
        d["id"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    )
    marketing_label = f"ED{ids_in_label_order.index(marketing['id']) + 1}"
    clash = ProposedCleanup(target=marketing_label, action="rename", new_name="Sales", note="Tidy up.")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_logistics_answer([clash]))
    items = await generate_blueprint(db_session, org_id)

    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    body = resp.json()
    assert body["accepted"] == len(items) - 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["title"] == "Sales"
    assert "already exists" in body["skipped"][0]["reason"]
    names = sorted(d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"])
    assert names == ["Marketing", "Operations", "Sales"]
    still_pending = (await client.get(f"{BLUEPRINT}?status=pending", headers=headers)).json()["data"]
    assert [i["title"] for i in still_pending] == ["Sales"]


@pytest.mark.asyncio
async def test_a_company_with_its_own_wrong_structure_is_cleaned_up(client, db_session, monkeypatch):
    """'Hr' is renamed to 'Human Resources' once Adaeze accepts the clean-up."""
    login, headers, org_id = await _org_with_dna(client, db_session, "bp_clean@example.com")
    await client.post(DEPARTMENTS, json={"name": "Hr"}, headers=headers)
    rename = ProposedCleanup(target="ED1", action="rename", new_name="Human Resources", note="Standard name.")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_logistics_answer([rename]))
    items = await generate_blueprint(db_session, org_id)

    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Human Resources').id}/approve", headers=headers)

    names = sorted(d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"])
    assert names == ["Human Resources"]
