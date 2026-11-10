"""Reshaping a plan under review: add a left-out item back, and merge two suggested items.

Scenario: Adaeze's logistics plan has Operations and Customer Support. She decides one
team can do both and merges Support into Operations; she also decides 'Fleet Admin',
which the plan left out, deserves its own department after all.
"""
import pytest

from app.modules.blueprint.schemas import (
    BlueprintAnswer,
    ProposedDepartment,
    ProposedFold,
    ProposedKPI,
    ProposedObjective,
    ProposedKeyResult,
    ProposedPosition,
)
from tests.blueprint.test_blueprint_flow import (
    BLUEPRINT,
    DEPARTMENTS,
    POSITIONS,
    _auth,
    _by_title,
    _generate,
)
from tests.conftest import register_verified_and_login


def _dept(ref, name, share):
    return ProposedDepartment(
        ref=ref, name=name, is_critical=True, revenue_allocation_pct=share,
        profit_margin_pct=20, rationale="Needed.",
    )


def _pos(ref, title, department, reports_to=None, critical=False):
    extra = {"is_critical": True, "criticality_type": "operational", "risk_level": "high"} if critical else {}
    return ProposedPosition(
        ref=ref, title=title, department=department, reports_to=reports_to, rationale="Needed.", **extra
    )


def _kpi(name, department, weight):
    return ProposedKPI(name=name, department=department, weight=weight, rationale="Tracks it.")


def _plan() -> BlueprintAnswer:
    """Operations (Director <- Dispatch Manager <- Driver Lead) and Customer Support (Support Lead)."""
    return BlueprintAnswer(
        departments=[_dept("D1", "Operations", 60), _dept("D2", "Customer Support", 40)],
        positions=[
            _pos("P1", "Operations Director", "D1"),
            _pos("P2", "Dispatch Manager", "D1", "P1"),
            _pos("P3", "Driver Lead", "D1", "P2"),
            _pos("P4", "Support Lead", "D2", "P1", critical=True),
        ],
        objectives=[
            ProposedObjective(
                ref="O1", title="Happy customers", department="D2",
                key_results=[ProposedKeyResult(ref="K1", description="Answer 90% of calls in a minute")],
                rationale="Retention.",
            )
        ],
        kpis=[
            _kpi("On-time rate", "D1", 100),
            _kpi("Answer speed", "D2", 100),
        ],
        cleanups=[],
        folded=[
            ProposedFold(kind="department", name="Fleet Admin", covered_by="D1", reason="Operations can do it."),
            ProposedFold(kind="position", name="Route Planner", covered_by="P2", reason="Dispatch can plan routes."),
        ],
    )


async def _listed(client, headers):
    """The plan as the screen reads it, by title."""
    data = (await client.get(BLUEPRINT, headers=headers)).json()["data"]
    return {i["title"]: i for i in data}


async def _plan_for(client, db_session, monkeypatch, email):
    _, headers, _, items = await _generate(client, db_session, monkeypatch, email, answer=_plan())
    return headers, items


# ---------------------------------------------------------------- merge departments

@pytest.mark.asyncio
async def test_merging_a_department_moves_its_roles_objectives_kpis_and_capital(client, db_session, monkeypatch):
    """Support merged into Operations: Operations now has everything and all 100% of the capital."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_dept1@example.com")
    support, operations = _by_title(items, "Customer Support"), _by_title(items, "Operations")

    resp = await client.post(f"{BLUEPRINT}/{support.id}/merge", json={"target_id": str(operations.id)}, headers=headers)

    assert resp.status_code == 200
    plan = await _listed(client, headers)
    assert (plan["Customer Support"]["kind"], plan["Customer Support"]["folded_into_ref"]) == ("folded", "D1")
    assert plan["Support Lead"]["department_ref"] == "D1"
    assert plan["Happy customers"]["department_ref"] == "D1"
    assert float(plan["Operations"]["revenue_allocation_pct"]) == 100.0
    kpi_weights = [float(plan[n]["kpi_weight"]) for n in ("On-time rate", "Answer speed")]
    assert kpi_weights == [50.0, 50.0]
    assert plan["Answer speed"]["department_ref"] == "D1"


@pytest.mark.asyncio
async def test_the_merged_plan_creates_only_the_merged_department(client, db_session, monkeypatch):
    """After the merge, Accept all builds one department, and the Support Lead sits inside it."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_dept2@example.com")
    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Customer Support').id}/merge",
        json={"target_id": str(_by_title(items, 'Operations').id)}, headers=headers,
    )

    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    departments = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    positions = (await client.get(POSITIONS, headers=headers)).json()["data"]
    assert [d["name"] for d in departments] == ["Operations"]
    support_lead = next(p for p in positions if p["title"] == "Support Lead")
    assert support_lead["department_id"] == departments[0]["id"]


# ---------------------------------------------------------------- merge roles

@pytest.mark.asyncio
async def test_merging_a_role_makes_its_reports_answer_to_the_other(client, db_session, monkeypatch):
    """Dispatch Manager merged into Operations Director: Driver Lead now reports to the Director."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_pos1@example.com")

    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Dispatch Manager').id}/merge",
        json={"target_id": str(_by_title(items, 'Operations Director').id)}, headers=headers,
    )

    plan = await _listed(client, headers)
    assert plan["Dispatch Manager"]["kind"] == "folded"
    assert plan["Driver Lead"]["reports_to_ref"] == "P1"


@pytest.mark.asyncio
async def test_merging_a_role_into_its_own_report_does_not_make_a_loop(client, db_session, monkeypatch):
    """Director merged into Dispatch Manager (who reports to the Director): Dispatch becomes the top."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_pos2@example.com")

    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Operations Director').id}/merge",
        json={"target_id": str(_by_title(items, 'Dispatch Manager').id)}, headers=headers,
    )

    plan = await _listed(client, headers)
    assert plan["Dispatch Manager"]["reports_to_ref"] is None
    assert plan["Support Lead"]["reports_to_ref"] == "P2"
    assert plan["Driver Lead"]["reports_to_ref"] == "P2"


@pytest.mark.asyncio
async def test_a_merged_critical_role_makes_the_target_critical(client, db_session, monkeypatch):
    """Support Lead is critical; merged into the non-critical Dispatch Manager, it passes that on."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_pos3@example.com")

    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Support Lead').id}/merge",
        json={"target_id": str(_by_title(items, 'Dispatch Manager').id)}, headers=headers,
    )

    target = (await _listed(client, headers))["Dispatch Manager"]
    assert (target["is_critical"], target["criticality_type"], target["risk_level"]) == (True, "operational", "high")


# ---------------------------------------------------------------- merge into what exists

async def _real_id(client, headers, url, field, value):
    """The id of the real department or position with this name or title."""
    rows = (await client.get(url, headers=headers)).json()["data"]
    return next(r["id"] for r in rows if r[field] == value)


@pytest.mark.asyncio
async def test_a_suggested_department_can_be_merged_into_one_already_added(client, db_session, monkeypatch):
    """Operations is added (real); Support is merged into it: its roles move there, and it takes all the capital."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_ex1@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/approve", headers=headers)
    operations_id = await _real_id(client, headers, DEPARTMENTS, "name", "Operations")

    resp = await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Customer Support').id}/merge",
        json={"existing_id": operations_id}, headers=headers,
    )

    assert resp.status_code == 200
    plan = await _listed(client, headers)
    assert (plan["Customer Support"]["kind"], plan["Customer Support"]["department_id"]) == ("folded", operations_id)
    assert (plan["Support Lead"]["department_id"], plan["Support Lead"]["department_ref"]) == (operations_id, None)
    real = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    assert float(real[0]["revenue_allocation_percentage"]) == 100.0


@pytest.mark.asyncio
async def test_the_moved_roles_are_created_inside_the_real_department(client, db_session, monkeypatch):
    """After the merge, Accept all puts the Support Lead in the real Operations department."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_ex2@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/approve", headers=headers)
    operations_id = await _real_id(client, headers, DEPARTMENTS, "name", "Operations")
    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Customer Support').id}/merge",
        json={"existing_id": operations_id}, headers=headers,
    )

    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)

    departments = (await client.get(DEPARTMENTS, headers=headers)).json()["data"]
    assert [d["name"] for d in departments] == ["Operations"]
    assert await _real_id(client, headers, POSITIONS, "title", "Support Lead")
    support_lead = next(p for p in (await client.get(POSITIONS, headers=headers)).json()["data"] if p["title"] == "Support Lead")
    assert support_lead["department_id"] == operations_id


@pytest.mark.asyncio
async def test_the_moved_kpis_share_the_real_departments_free_weight(client, db_session, monkeypatch):
    """Operations has no KPIs yet: its own suggested KPI and Support's now split the 100% between them."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_ex3@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/approve", headers=headers)
    operations_id = await _real_id(client, headers, DEPARTMENTS, "name", "Operations")

    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Customer Support').id}/merge",
        json={"existing_id": operations_id}, headers=headers,
    )

    plan = await _listed(client, headers)
    assert [float(plan[n]["kpi_weight"]) for n in ("On-time rate", "Answer speed")] == [50.0, 50.0]
    assert plan["Answer speed"]["department_id"] == operations_id


@pytest.mark.asyncio
async def test_kpis_that_no_longer_fit_are_set_aside_and_the_note_says_so(client, db_session, monkeypatch):
    """Operations already has its full 100% of KPIs: Support's KPI is skipped and the reason is recorded."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_ex4@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'On-time rate').id}/approve", headers=headers)
    operations_id = await _real_id(client, headers, DEPARTMENTS, "name", "Operations")

    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Customer Support').id}/merge",
        json={"existing_id": operations_id}, headers=headers,
    )

    plan = await _listed(client, headers)
    assert plan["Answer speed"]["status"] == "rejected"
    assert "full set of KPIs" in plan["Customer Support"]["rationale"]


@pytest.mark.asyncio
async def test_a_suggested_role_can_be_merged_into_one_already_added(client, db_session, monkeypatch):
    """The Director is added (real); Dispatch Manager is merged into it: Driver Lead now reports to the real Director."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_ex5@example.com")
    await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations Director').id}/approve", headers=headers)
    director_id = await _real_id(client, headers, POSITIONS, "title", "Operations Director")

    await client.post(
        f"{BLUEPRINT}/{_by_title(items, 'Dispatch Manager').id}/merge",
        json={"existing_id": director_id}, headers=headers,
    )

    plan = await _listed(client, headers)
    assert (plan["Dispatch Manager"]["kind"], plan["Dispatch Manager"]["position_id"]) == ("folded", director_id)
    assert (plan["Driver Lead"]["reports_to_position_id"], plan["Driver Lead"]["reports_to_ref"]) == (director_id, None)


@pytest.mark.asyncio
async def test_merging_into_an_unknown_real_row_is_404_and_the_target_choice_is_checked(client, db_session, monkeypatch):
    """A made-up real id is a 404; giving both targets, or neither, is a 422."""
    import uuid

    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_ex6@example.com")
    support, operations = _by_title(items, "Customer Support"), _by_title(items, "Operations")
    url = f"{BLUEPRINT}/{support.id}/merge"

    unknown = await client.post(url, json={"existing_id": str(uuid.uuid4())}, headers=headers)
    both = await client.post(url, json={"existing_id": str(uuid.uuid4()), "target_id": str(operations.id)}, headers=headers)
    neither = await client.post(url, json={}, headers=headers)

    assert [r.status_code for r in (unknown, both, neither)] == [404, 422, 422]


# ---------------------------------------------------------------- merge refusals

@pytest.mark.asyncio
async def test_merge_refuses_the_wrong_pairs(client, db_session, monkeypatch):
    """Into itself, a department into a role, and a left-out note are all refused with 422."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_bad1@example.com")
    operations, director = _by_title(items, "Operations"), _by_title(items, "Operations Director")
    note = _by_title(items, "Fleet Admin")

    into_itself = await client.post(f"{BLUEPRINT}/{operations.id}/merge", json={"target_id": str(operations.id)}, headers=headers)
    mixed = await client.post(f"{BLUEPRINT}/{operations.id}/merge", json={"target_id": str(director.id)}, headers=headers)
    a_note = await client.post(f"{BLUEPRINT}/{note.id}/merge", json={"target_id": str(operations.id)}, headers=headers)

    assert [r.status_code for r in (into_itself, mixed, a_note)] == [422, 422, 422]


@pytest.mark.asyncio
async def test_merge_with_an_unknown_target_is_404_and_with_an_added_one_409(client, db_session, monkeypatch):
    """A made-up target is not found; an item that is already added cannot be merged."""
    import uuid

    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_bad2@example.com")
    support, operations = _by_title(items, "Customer Support"), _by_title(items, "Operations")

    unknown = await client.post(f"{BLUEPRINT}/{support.id}/merge", json={"target_id": str(uuid.uuid4())}, headers=headers)
    await client.post(f"{BLUEPRINT}/{operations.id}/approve", headers=headers)
    added = await client.post(f"{BLUEPRINT}/{support.id}/merge", json={"target_id": str(operations.id)}, headers=headers)

    assert (unknown.status_code, added.status_code) == (404, 409)


@pytest.mark.asyncio
async def test_an_employee_cannot_reshape_the_plan(client, db_session, monkeypatch):
    """Only HR and executives reshape the plan: a plain account gets 403."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_403@example.com")
    outsider = _auth(await register_verified_and_login(client, email="rs_403_other@example.com"))

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Fleet Admin').id}/add-separately", headers=outsider)

    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------- add separately

@pytest.mark.asyncio
async def test_a_left_out_department_can_come_back_and_be_added(client, db_session, monkeypatch):
    """'Fleet Admin' becomes a pending department; adding it creates the real department."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_add1@example.com")
    note = _by_title(items, "Fleet Admin")

    resp = await client.post(f"{BLUEPRINT}/{note.id}/add-separately", headers=headers)

    body = resp.json()
    assert (resp.status_code, body["kind"], body["status"], body["folded_into_ref"]) == (200, "department", "pending", None)
    approved = await client.post(f"{BLUEPRINT}/{note.id}/approve", headers=headers)
    assert approved.status_code == 200
    names = [d["name"] for d in (await client.get(DEPARTMENTS, headers=headers)).json()["data"]]
    assert names == ["Fleet Admin"]


@pytest.mark.asyncio
async def test_a_left_out_role_comes_back_in_the_covering_roles_department(client, db_session, monkeypatch):
    """'Route Planner' (covered by Dispatch Manager, in Operations) returns inside Operations, reporting to it."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_add2@example.com")

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Route Planner').id}/add-separately", headers=headers)

    body = resp.json()
    assert (body["kind"], body["department_ref"], body["reports_to_ref"]) == ("position", "D1", "P2")
    await client.post(f"{BLUEPRINT}/accept-all", headers=headers)
    positions = {p["title"]: p for p in (await client.get(POSITIONS, headers=headers)).json()["data"]}
    assert positions["Route Planner"]["reports_to_position_id"] == positions["Dispatch Manager"]["id"]


@pytest.mark.asyncio
async def test_only_a_left_out_item_can_be_added_back(client, db_session, monkeypatch):
    """Adding a normal department 'separately' is refused with 422."""
    headers, items = await _plan_for(client, db_session, monkeypatch, "rs_add3@example.com")

    resp = await client.post(f"{BLUEPRINT}/{_by_title(items, 'Operations').id}/add-separately", headers=headers)

    assert resp.status_code == 422
