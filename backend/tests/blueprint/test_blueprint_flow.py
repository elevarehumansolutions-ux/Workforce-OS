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
    ProposedFold,
    ProposedKeyResult,
    ProposedKPI,
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
    """Operations (Director <- Manager), one objective with two key results, two KPIs."""
    return BlueprintAnswer(
        departments=[
            ProposedDepartment(
                ref="D1", name="Operations", is_critical=True, revenue_allocation_pct=40,
                profit_margin_pct=25, rationale="Moves the goods.",
            )
        ],
        positions=[
            ProposedPosition(
                ref="P1", title="Operations Director", department="D1", is_critical=True,
                criticality_type="operational", risk_level="high", rationale="Leads.",
            ),
            ProposedPosition(
                ref="P2", title="Dispatch Manager", department="D1", reports_to="P1", rationale="Routes."
            ),
        ],
        objectives=[
            ProposedObjective(
                ref="O1", title="Deliver on time", department="D1",
                key_results=[
                    ProposedKeyResult(ref="K1", description="95% on-time deliveries"),
                    ProposedKeyResult(ref="K2", description="Cut average transit time to 2 days"),
                ],
                rationale="Customers value speed.",
            )
        ],
        kpis=[
            ProposedKPI(
                name="On-time delivery rate", department="D1", key_result="K1", weight=60,
                target_value=95, unit="%", rationale="Direct measure of K1.",
            ),
            ProposedKPI(
                name="Average transit time", department="D1", key_result="K2", weight=40,
                target_value=2, unit="days", lower_is_better=True, rationale="Direct measure of K2.",
            ),
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
    """Nothing real is created: 1 department, 2 positions, 1 objective, 2 key results, 2 KPIs, all pending."""
    _, headers, org_id, items = await _generate(client, db_session, monkeypatch, "bp_gen1@example.com")

    assert sorted(i.kind for i in items) == [
        "department", "key_result", "key_result", "kpi", "kpi", "objective", "position", "position",
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
async def test_skipping_a_department_skips_everything_under_it_in_the_same_step(client, db_session, monkeypatch):
    """Adaeze skips Operations: its roles, objective, key results and KPIs are skipped with it, none left waiting."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_rej@example.com")

    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/reject", headers=headers)

    rows = (await client.get(BLUEPRINT, headers=headers)).json()["data"]
    assert {row["status"] for row in rows} == {"rejected"}
    assert len(rows) == 8
    assert (await client.get(POSITIONS, headers=headers)).json()["data"] == []


@pytest.mark.asyncio
async def test_a_child_of_a_skipped_department_cannot_be_added_afterwards(client, db_session, monkeypatch):
    """Trying its Director after the skip is refused: it was already skipped with its department."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_rej2@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/reject", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations Director').id}/approve", headers=headers)

    assert (resp.status_code, resp.json()["code"]) == (409, "BLUEPRINT_ITEM_ALREADY_REVIEWED")
    assert (await client.get(POSITIONS, headers=headers)).json()["data"] == []


@pytest.mark.asyncio
async def test_skipping_an_objective_skips_its_key_results_but_not_its_kpis(client, db_session, monkeypatch):
    """The KPI's link to a key result is optional, so the KPIs stay waiting."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_rej3@example.com")

    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Deliver on time').id}/reject", headers=headers)

    rows = (await client.get(BLUEPRINT, headers=headers)).json()["data"]
    status_of = {row["title"]: row["status"] for row in rows}
    assert status_of["95% on-time deliveries"] == "rejected"
    assert status_of["Cut average transit time to 2 days"] == "rejected"
    assert status_of["On-time delivery rate"] == "pending"
    assert status_of["Operations"] == "pending"


@pytest.mark.asyncio
async def test_a_department_cannot_be_skipped_once_one_of_its_roles_was_added(client, db_session, monkeypatch):
    """Adding the Director added Operations too, so Operations is real and can no longer be skipped."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_rej4@example.com")
    director = _by_title(items, "Operations Director")
    await client.post(f"{BLUEPRINT}/{director.id}/approve", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/reject", headers=headers)

    assert resp.status_code == 409


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


# ------------------------------------------------- criticality and capital share

@pytest.mark.asyncio
async def test_approved_items_carry_the_ais_critical_flags_and_capital_share(client, db_session, monkeypatch):
    """The user is never asked: Operations is created critical with all the capital and a margin.

    It is the only critical department, so it gets 100%, with a 25% margin; the Director is
    critical (operational, high).
    """
    _, headers, _, _ = await _generate(client, db_session, monkeypatch, "bp_crit1@example.com")

    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    department = (await client.get(DEPARTMENTS, headers=headers)).json()["data"][0]
    assert department["is_critical"] is True
    assert float(department["revenue_allocation_percentage"]) == 100
    assert float(department["profit_margin_percentage"]) == 25
    positions = {p["title"]: p for p in (await client.get(POSITIONS, headers=headers)).json()["data"]}
    director = positions["Operations Director"]
    assert (director["is_critical"], director["criticality_type"], director["risk_level"]) == (
        True, "operational", "high",
    )
    assert positions["Dispatch Manager"]["is_critical"] is False


@pytest.mark.asyncio
async def test_the_proposal_lists_show_the_critical_flags_before_anything_is_approved(
    client, db_session, monkeypatch
):
    """The review screen can show the AI's decision: GET /blueprint carries it on the pending items."""
    _, headers, _, _ = await _generate(client, db_session, monkeypatch, "bp_crit2@example.com")

    items = (await client.get(f"{BLUEPRINT}?status=pending", headers=headers)).json()["data"]

    department = next(i for i in items if i["kind"] == "department")
    assert (department["is_critical"], float(department["revenue_allocation_pct"])) == (True, 100)
    assert float(department["profit_margin_pct"]) == 25
    director = next(i for i in items if i["title"] == "Operations Director")
    assert (director["is_critical"], director["criticality_type"], director["risk_level"]) == (
        True, "operational", "high",
    )


def _three_critical_departments() -> BlueprintAnswer:
    """Sales 50, Operations 30, Marketing 20: the capital split as Claude proposed it."""
    return BlueprintAnswer(
        departments=[
            ProposedDepartment(ref="D1", name="Sales", is_critical=True, revenue_allocation_pct=50,
                               profit_margin_pct=30, rationale="Brings in revenue."),
            ProposedDepartment(ref="D2", name="Operations", is_critical=True, revenue_allocation_pct=30,
                               profit_margin_pct=20, rationale="Delivers."),
            ProposedDepartment(ref="D3", name="Marketing", is_critical=True, revenue_allocation_pct=20,
                               profit_margin_pct=15, rationale="Finds customers."),
        ],
        positions=[], objectives=[], kpis=[], cleanups=[],
    )


async def _shares(client, headers) -> dict:
    rows = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    return {d["name"]: float(d["revenue_allocation_percentage"]) for d in rows}


@pytest.mark.asyncio
async def test_skipping_a_department_hands_its_capital_to_the_others(client, db_session, monkeypatch):
    """Skipping Marketing re-balances: the capital is always split, never left partly unallocated.

    Sales stays 50 while all three are in play; skip Marketing and Sales becomes 62.5;
    approve Operations and it takes 37.5.
    """
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_split1@example.com", answer=_three_critical_departments()
    )

    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Sales').id}/approve", headers=headers)
    assert await _shares(client, headers) == {"Sales": 50.0}

    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Marketing').id}/reject", headers=headers)
    assert await _shares(client, headers) == {"Sales": 62.5}

    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/approve", headers=headers)
    shares = await _shares(client, headers)
    assert shares == {"Sales": 62.5, "Operations": 37.5}
    assert sum(shares.values()) == 100


@pytest.mark.asyncio
async def test_accepting_all_after_skipping_one_still_splits_100(client, db_session, monkeypatch):
    """Skip Operations, then accept the rest: Sales 71.43 and Marketing 28.57, adding up to 100."""
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_split2@example.com", answer=_three_critical_departments()
    )
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/reject", headers=headers)

    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    shares = await _shares(client, headers)
    assert shares == {"Sales": 71.43, "Marketing": 28.57}
    assert round(sum(shares.values()), 2) == 100


@pytest.mark.asyncio
async def test_each_department_keeps_its_own_profit_margin(client, db_session, monkeypatch):
    """The estimated margins from the proposal land on the real departments."""
    _, headers, _, _ = await _generate(
        client, db_session, monkeypatch, "bp_split3@example.com", answer=_three_critical_departments()
    )

    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    rows = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    assert {d["name"]: float(d["profit_margin_percentage"]) for d in rows} == {
        "Sales": 30.0, "Operations": 20.0, "Marketing": 15.0,
    }


# ------------------------------------------------------------------------- KPIs

KPIS = "/api/v1/kpis"


async def _kpis_of(client, headers):
    return (await client.get(f"{KPIS}?limit=100", headers=headers)).json()["data"]


@pytest.mark.asyncio
async def test_accept_all_creates_the_kpis_linked_to_their_key_results(client, db_session, monkeypatch):
    """The two KPIs become real, weights 60 + 40, each pointing at the key result it measures."""
    _, headers, _, _ = await _generate(client, db_session, monkeypatch, "bp_kpi1@example.com")

    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    assert resp.json()["skipped"] == []
    kpis = {k["name"]: k for k in await _kpis_of(client, headers)}
    assert set(kpis) == {"On-time delivery rate", "Average transit time"}
    assert float(kpis["On-time delivery rate"]["weight"]) == 60
    assert float(kpis["Average transit time"]["weight"]) == 40
    assert kpis["On-time delivery rate"]["is_inverse"] is False
    assert kpis["Average transit time"]["is_inverse"] is True
    assert float(kpis["On-time delivery rate"]["target_value"]) == 95
    assert kpis["On-time delivery rate"]["unit"] == "%"
    okr = (await client.get(OKRS, headers=headers)).json()["data"][0]
    key_results = {
        k["description"]: k["id"]
        for k in (await client.get(f"{OKRS}/{okr['id']}/key-results", headers=headers)).json()["data"]
    }
    assert kpis["On-time delivery rate"]["key_result_id"] == key_results["95% on-time deliveries"]
    assert kpis["Average transit time"]["key_result_id"] == key_results["Cut average transit time to 2 days"]


@pytest.mark.asyncio
async def test_approving_a_kpi_creates_its_department_key_result_and_objective_first(
    client, db_session, monkeypatch
):
    """One KPI approved: Operations, the objective and just that key result are created too."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_kpi2@example.com")

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'On-time delivery rate').id}/approve", headers=headers)

    assert resp.status_code == 200
    assert [d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"]] == ["Operations"]
    okr = (await client.get(OKRS, headers=headers)).json()["data"][0]
    key_results = (await client.get(f"{OKRS}/{okr['id']}/key-results", headers=headers)).json()["data"]
    assert [k["description"] for k in key_results] == ["95% on-time deliveries"]
    kpis = await _kpis_of(client, headers)
    assert [k["name"] for k in kpis] == ["On-time delivery rate"]
    assert kpis[0]["key_result_id"] == key_results[0]["id"]


@pytest.mark.asyncio
async def test_a_kpi_whose_key_result_was_skipped_is_still_created_without_the_link(
    client, db_session, monkeypatch
):
    """The link is optional: rejecting the key result must not block the KPI."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_kpi3@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, '95% on-time deliveries').id}/reject", headers=headers)

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'On-time delivery rate').id}/approve", headers=headers)

    assert resp.status_code == 200
    kpis = await _kpis_of(client, headers)
    assert [(k["name"], k["key_result_id"]) for k in kpis] == [("On-time delivery rate", None)]


def _kpis_for_existing_department(*weights):
    """An answer that only proposes KPIs for the company's existing department (ED1)."""
    return BlueprintAnswer(
        departments=[],
        positions=[],
        objectives=[],
        kpis=[
            ProposedKPI(name=f"Sales KPI {n}", department="ED1", weight=w, rationale="Needed.")
            for n, w in enumerate(weights)
        ],
        cleanups=[],
    )


@pytest.mark.asyncio
async def test_an_existing_departments_free_weight_is_respected(client, db_session, monkeypatch):
    """Sales already has a 70% KPI: the AI's two KPIs share the remaining 30%, and all are created."""
    login, headers, org_id = await _org_with_dna(client, db_session, "bp_kpi4@example.com")
    sales = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)).json()
    await client.post(KPIS, json={"department_id": sales["id"], "name": "Revenue", "weight": 70}, headers=headers)
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_kpis_for_existing_department(50, 50))
    items = await generate_blueprint(db_session, org_id)

    assert sorted(float(i.kpi_weight) for i in items) == [15.0, 15.0]
    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    assert resp.json()["skipped"] == []
    assert sum(float(k["weight"]) for k in await _kpis_of(client, headers)) == 100


@pytest.mark.asyncio
async def test_a_department_with_a_full_set_of_kpis_gets_no_proposals(client, db_session, monkeypatch):
    """Sales is at 100%: even if Claude proposes KPIs for it, none are saved."""
    login, headers, org_id = await _org_with_dna(client, db_session, "bp_kpi5@example.com")
    sales = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)).json()
    await client.post(KPIS, json={"department_id": sales["id"], "name": "Revenue", "weight": 100}, headers=headers)
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_kpis_for_existing_department(100))

    assert await generate_blueprint(db_session, org_id) == []


@pytest.mark.asyncio
async def test_suggested_kpis_shrink_to_the_room_a_hand_made_kpi_left(client, db_session, monkeypatch):
    """HR adds a 90% KPI by hand after the draft: the two 50% suggestions are scaled to 5% each and added."""
    login, headers, org_id = await _org_with_dna(client, db_session, "bp_kpi6@example.com")
    sales = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)).json()
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_kpis_for_existing_department(50, 50))
    await generate_blueprint(db_session, org_id)
    await client.post(KPIS, json={"department_id": sales["id"], "name": "Hand made", "weight": 90}, headers=headers)

    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    body = resp.json()
    assert body["accepted"] == 2
    assert body["skipped"] == []
    weights = sorted(float(k["weight"]) for k in await _kpis_of(client, headers))
    assert weights == [5.0, 5.0, 90.0]


@pytest.mark.asyncio
async def test_a_kpi_is_refused_with_a_clear_message_when_the_department_has_no_room(client, db_session, monkeypatch):
    """HR's hand-made KPIs use all 100%: accept-all skips the suggestions and says what to do."""
    login, headers, org_id = await _org_with_dna(client, db_session, "bp_kpi6b@example.com")
    sales = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=headers)).json()
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_kpis_for_existing_department(50, 50))
    await generate_blueprint(db_session, org_id)
    await client.post(KPIS, json={"department_id": sales["id"], "name": "Hand made", "weight": 100}, headers=headers)

    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    body = resp.json()
    assert body["accepted"] == 0
    assert len(body["skipped"]) == 2
    assert "Lower another KPI's weight" in body["skipped"][0]["reason"]
    assert [k["name"] for k in await _kpis_of(client, headers)] == ["Hand made"]


@pytest.mark.asyncio
async def test_a_suggested_kpis_weight_can_be_corrected_when_adding_it(client, db_session, monkeypatch):
    """The 60% KPI is added with 55% (room is plentiful, so the number the owner typed is kept)."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_kpi7@example.com")
    kpi = _by_title(items, "On-time delivery rate")
    other = _by_title(items, "Average transit time")
    await client.post(f"{BLUEPRINT}/{other.id}/reject", headers=headers)  # leave the whole 100% free

    resp = await _edit(client, headers, kpi, kpi_weight="55")

    assert resp.status_code == 200
    real = next(k for k in await _kpis_of(client, headers) if k["name"] == "On-time delivery rate")
    assert float(real["weight"]) == 55


@pytest.mark.asyncio
async def test_a_kpi_weight_of_zero_or_over_100_is_a_422_and_null_is_refused(client, db_session, monkeypatch):
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_kpi8@example.com")
    kpi = _by_title(items, "On-time delivery rate")

    for bad in ("0", "101", "-5"):
        assert (await _edit(client, headers, kpi, kpi_weight=bad)).status_code == 422
    assert (await _edit(client, headers, kpi, kpi_weight=None)).status_code == 422
    assert await _kpis_of(client, headers) == []


# ------------------------------------------------ editing details before adding

async def _edit(client, headers, item, **fields):
    return await client.post(f"{BLUEPRINT}/{item.id}/edit", json={"title": item.title, **fields}, headers=headers)


@pytest.mark.asyncio
async def test_a_kpis_target_unit_and_direction_can_be_changed_before_adding(client, db_session, monkeypatch):
    """Target 95 % becomes 99 'percent', and the KPI is now 'lower is better'; the real KPI has them."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_ed1@example.com")
    kpi = _by_title(items, "On-time delivery rate")

    resp = await _edit(client, headers, kpi, kpi_target_value="99", kpi_unit="percent", kpi_is_inverse=True)

    assert resp.status_code == 200
    real = next(k for k in await _kpis_of(client, headers) if k["name"] == "On-time delivery rate")
    assert (float(real["target_value"]), real["unit"], real["is_inverse"]) == (99, "percent", True)


@pytest.mark.asyncio
async def test_an_explicit_null_clears_a_kpis_target_and_leaving_it_out_keeps_it(client, db_session, monkeypatch):
    """An explicit null removes the target; an edit that does not mention it leaves 95 alone."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_ed2@example.com")
    cleared = _by_title(items, "On-time delivery rate")
    kept = _by_title(items, "Average transit time")

    await _edit(client, headers, cleared, kpi_target_value=None)
    await _edit(client, headers, kept, kpi_unit="working days")

    real = {k["name"]: k for k in await _kpis_of(client, headers)}
    assert real["On-time delivery rate"]["target_value"] is None
    assert float(real["Average transit time"]["target_value"]) == 2
    assert real["Average transit time"]["unit"] == "working days"


@pytest.mark.asyncio
async def test_a_detail_that_does_not_belong_to_the_kind_is_refused(client, db_session, monkeypatch):
    """A KPI field on a position, or a share on a KPI, is a 422 and nothing changes."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_ed3@example.com")

    on_position = await _edit(client, headers, _by_title(items, "Operations Director"), kpi_unit="days")
    on_kpi = await _edit(client, headers, _by_title(items, "On-time delivery rate"), revenue_allocation_pct="50")
    no_direction = await _edit(client, headers, _by_title(items, "Average transit time"), kpi_is_inverse=None)

    assert (on_position.status_code, on_kpi.status_code, no_direction.status_code) == (422, 422, 422)
    still_pending = (await client.get(f"{BLUEPRINT}?status=pending", headers=headers)).json()["pagination"]["total"]
    assert still_pending == len(items)


@pytest.mark.asyncio
async def test_out_of_range_numbers_are_refused(client, db_session, monkeypatch):
    """A negative target and a share above 100 are 422."""
    _, headers, _, items = await _generate(client, db_session, monkeypatch, "bp_ed4@example.com")

    negative = await _edit(client, headers, _by_title(items, "On-time delivery rate"), kpi_target_value="-1")
    too_big = await _edit(client, headers, _by_title(items, "Operations"), revenue_allocation_pct="120")

    assert (negative.status_code, too_big.status_code) == (422, 422)


@pytest.mark.asyncio
async def test_changing_one_departments_share_keeps_the_split_at_100(client, db_session, monkeypatch):
    """Sales 50 -> 60: Operations (30) and Marketing (20) shrink in proportion to 24 and 16."""
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_ed5@example.com", answer=_three_critical_departments()
    )

    await _edit(client, headers, _by_title(items, "Sales"), revenue_allocation_pct="60")
    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    shares = await _shares(client, headers)
    assert shares == {"Sales": 60.0, "Operations": 24.0, "Marketing": 16.0}
    assert sum(shares.values()) == 100


@pytest.mark.asyncio
async def test_a_departments_margin_can_be_changed_before_adding(client, db_session, monkeypatch):
    """The 30% margin becomes 45% on the real department."""
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_ed6@example.com", answer=_three_critical_departments()
    )

    await _edit(client, headers, _by_title(items, "Sales"), profit_margin_pct="45")

    rows = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    assert float(next(d for d in rows if d["name"] == "Sales")["profit_margin_percentage"]) == 45


@pytest.mark.asyncio
async def test_the_edited_share_shows_on_the_proposal_list_too(client, db_session, monkeypatch):
    """GET /blueprint carries the new raw shares so the screen can show them before anything is added."""
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_ed7@example.com", answer=_three_critical_departments()
    )

    await _edit(client, headers, _by_title(items, "Marketing"), revenue_allocation_pct="10")

    listed = {i["title"]: float(i["revenue_allocation_pct"]) for i in (await client.get(BLUEPRINT, headers=headers)).json()["data"] if i["kind"] == "department"}
    assert round(sum(listed.values()), 1) == 100
    assert listed["Marketing"] == 10.0


def _answer_with_a_fold() -> BlueprintAnswer:
    """The logistics plan, plus: 'Fleet Admin' is left out because Operations (D1) covers it."""
    answer = _logistics_answer()
    answer.folded = [
        ProposedFold(
            kind="department", name="Fleet Admin", covered_by="D1",
            reason="Operations can run the vehicles in a company this size.",
        )
    ]
    return answer


@pytest.mark.asyncio
async def test_a_folded_note_is_listed_and_approving_it_creates_nothing(client, db_session, monkeypatch):
    """Adaeze sees 'Fleet Admin: covered by Operations'; marking it seen adds no department."""
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_fold1@example.com", answer=_answer_with_a_fold()
    )
    note = _by_title(items, "Fleet Admin")

    listed = (await client.get(BLUEPRINT, headers=headers)).json()["data"]
    listed_note = next(i for i in listed if i["id"] == str(note.id))
    resp = await client.post(f"{BLUEPRINT}/{note.id}/approve", headers=headers)

    assert (listed_note["kind"], listed_note["folded_into_ref"]) == ("folded", "D1")
    assert resp.status_code == 200
    assert (resp.json()["status"], resp.json()["created_entity_id"]) == ("approved", None)
    assert (await client.get(DEPARTMENTS, headers=headers)).json()["data"] == []


@pytest.mark.asyncio
async def test_accept_all_marks_a_folded_note_seen_and_still_builds_the_rest(client, db_session, monkeypatch):
    """The note is counted among the accepted items and no 'Fleet Admin' department appears."""
    _, headers, _, items = await _generate(
        client, db_session, monkeypatch, "bp_fold2@example.com", answer=_answer_with_a_fold()
    )

    resp = await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    assert resp.json() == {"accepted": len(items), "skipped": []}
    names = [d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"]]
    assert names == ["Operations"]
