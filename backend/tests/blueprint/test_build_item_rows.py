"""How Claude's answer is checked before anything is saved (pure: no database, no API).

Scenario: Kelechi runs a logistics company. Claude proposes a structure; the
code keeps what makes sense and drops what Claude invented or got wrong.
"""
import uuid
from decimal import Decimal

from app.modules.blueprint.generation import KnownStructure, build_item_rows, normalize_weights
from app.modules.blueprint.schemas import (
    BlueprintAnswer,
    ProposedCleanup,
    ProposedDepartment,
    ProposedKeyResult,
    ProposedKPI,
    ProposedObjective,
    ProposedPosition,
)

ORG = uuid.uuid4()
BATCH = uuid.uuid4()
SALES_ID = uuid.uuid4()
GM_ID = uuid.uuid4()


def _dept(ref, name):
    return ProposedDepartment(ref=ref, name=name, rationale="Needed.")


def _pos(ref, title, department, reports_to=None):
    return ProposedPosition(
        ref=ref, title=title, department=department, reports_to=reports_to, rationale="Needed."
    )


def _answer(departments=(), positions=(), objectives=(), cleanups=(), kpis=()):
    return BlueprintAnswer(
        departments=list(departments),
        positions=list(positions),
        objectives=list(objectives),
        kpis=list(kpis),
        cleanups=list(cleanups),
    )


def _kr(ref, text="a key result"):
    return ProposedKeyResult(ref=ref, description=text)


def _kpi(name, department, weight=50, key_result=None, **extra):
    return ProposedKPI(
        name=name, department=department, key_result=key_result, weight=weight, rationale="Tracks it.", **extra
    )


def _build(answer, *, with_existing=False, objective_titles=(), kpi_room=None):
    """Run build_item_rows; ``with_existing`` gives the company a 'Sales' dept and a 'General Manager'."""
    known = KnownStructure()
    department_names, position_names = {}, {}
    if with_existing:
        known.existing_department_ids = {"ED1": SALES_ID}
        known.existing_position_ids = {"EP1": GM_ID}
        department_names = {SALES_ID: "Sales"}
        position_names = {GM_ID: ("General Manager", SALES_ID)}
    return build_item_rows(
        answer,
        organization_id=ORG,
        batch_id=BATCH,
        known=known,
        department_names=department_names,
        position_names=position_names,
        existing_objective_titles=set(objective_titles),
        kpi_room=kpi_room,
    )


def _kinds(rows):
    return [row["kind"] for row in rows]


def test_a_position_inside_a_proposed_department_points_at_it_by_ref():
    """Position P1 is in new department D1: it carries department_ref, not an id."""
    rows = _build(_answer([_dept("D1", "Operations")], [_pos("P1", "Operations Manager", "D1")]))

    position = rows[1]
    assert (position["kind"], position["department_ref"], position["department_id"]) == (
        "position", "D1", None,
    )


def test_a_department_the_company_already_has_is_not_proposed_again():
    """Claude says 'sales ' (D1); the company has 'Sales': no new row, and D1 means the real one."""
    rows = _build(
        _answer([_dept("D1", "sales ")], [_pos("P1", "Sales Rep", "D1")]), with_existing=True
    )

    assert _kinds(rows) == ["position"]
    assert rows[0]["department_id"] == SALES_ID
    assert rows[0]["department_ref"] is None


def test_a_position_the_company_already_has_is_not_proposed_again():
    """'General Manager' already exists in Sales, so only the new 'Sales Rep' is proposed."""
    rows = _build(
        _answer([], [_pos("P1", "general  manager", "ED1"), _pos("P2", "Sales Rep", "ED1", "P1")]),
        with_existing=True,
    )

    assert [r["title"] for r in rows] == ["Sales Rep"]
    assert rows[0]["reports_to_position_id"] == GM_ID


def test_a_label_claude_invented_is_dropped():
    """A position in department 'D9' that was never proposed is dropped, not saved."""
    rows = _build(_answer([_dept("D1", "Operations")], [_pos("P1", "Ghost", "D9")]))

    assert _kinds(rows) == ["department"]


def test_an_invented_boss_leaves_the_position_without_one():
    """reports_to 'P7' does not exist: the position is kept, with no boss."""
    rows = _build(_answer([_dept("D1", "Operations")], [_pos("P1", "Analyst", "D1", "P7")]))

    assert rows[1]["reports_to_ref"] is None
    assert rows[1]["reports_to_position_id"] is None


def test_the_hierarchy_is_kept_when_it_is_sound():
    """Director <- Manager <- Analyst: each position names the one above it."""
    rows = _build(
        _answer(
            [_dept("D1", "Operations")],
            [
                _pos("P1", "Director", "D1"),
                _pos("P2", "Manager", "D1", "P1"),
                _pos("P3", "Analyst", "D1", "P2"),
            ],
        )
    )

    bosses = {r["ref"]: r["reports_to_ref"] for r in rows if r["kind"] == "position"}
    assert bosses == {"P1": None, "P2": "P1", "P3": "P2"}


def test_a_reporting_loop_is_cut():
    """A reports to B and B reports to A: that would be saved as a ring, so it is broken."""
    rows = _build(
        _answer(
            [_dept("D1", "Operations")],
            [_pos("P1", "A", "D1", "P2"), _pos("P2", "B", "D1", "P1")],
        )
    )

    bosses = [r["reports_to_ref"] for r in rows if r["kind"] == "position"]
    # Not both pointing at each other: at least one is now a top of the chart.
    assert None in bosses


def test_a_position_cannot_report_to_itself():
    """reports_to its own ref is ignored."""
    rows = _build(_answer([_dept("D1", "Ops")], [_pos("P1", "Solo", "D1", "P1")]))

    assert rows[1]["reports_to_ref"] is None


def test_an_objective_brings_its_key_results_capped_at_four():
    """Five key results come in; four are kept, and each points at its objective."""
    objective = ProposedObjective(
        ref="O1", title="Grow revenue", department=None,
        key_results=[_kr("K1", "a"), _kr("K2", "b"), _kr("K3", "c"), _kr("K4", "d"), _kr("K5", "e")],
        rationale="Core goal.",
    )

    rows = _build(_answer(objectives=[objective]))

    assert _kinds(rows) == ["objective"] + ["key_result"] * 4
    assert {r["objective_ref"] for r in rows[1:]} == {"O1"}


def test_an_objective_the_company_already_has_is_skipped():
    """'Grow Revenue' (any case) is already an OKR: not proposed again."""
    objective = ProposedObjective(
        ref="O1", title="grow  revenue", department=None, key_results=[_kr("K1", "x")], rationale="r",
    )

    rows = _build(_answer(objectives=[objective]), objective_titles=["grow revenue"])

    assert rows == []


def test_an_objective_for_an_unknown_department_is_dropped():
    """Better to lose it than to attach it to the wrong place or call it company-wide."""
    objective = ProposedObjective(
        ref="O1", title="Hit target", department="D5", key_results=[_kr("K1", "x")], rationale="r",
    )

    assert _build(_answer(objectives=[objective])) == []


def test_a_rename_cleanup_points_at_the_existing_department():
    """'Sales' renamed to 'Sales and Marketing': a rename item carrying the department id."""
    cleanup = ProposedCleanup(target="ED1", action="rename", new_name="Sales and Marketing", note="Clearer.")

    rows = _build(_answer(cleanups=[cleanup]), with_existing=True)

    assert (rows[0]["kind"], rows[0]["title"], rows[0]["department_id"]) == (
        "rename_department", "Sales and Marketing", SALES_ID,
    )


def test_a_review_cleanup_becomes_a_note_and_a_rename_to_the_same_name_does_too():
    """Nothing to rename to: the AI's note is kept as a note for a human."""
    review = ProposedCleanup(target="EP1", action="review", note="Looks like a duplicate of another role.")
    same = ProposedCleanup(target="ED1", action="rename", new_name="SALES", note="Check this.")

    rows = _build(_answer(cleanups=[review, same]), with_existing=True)

    assert _kinds(rows) == ["review_note", "review_note"]


def test_a_cleanup_aimed_at_something_never_shown_is_dropped():
    """'ED9' was never handed to Claude."""
    cleanup = ProposedCleanup(target="ED9", action="rename", new_name="X", note="n")

    assert _build(_answer(cleanups=[cleanup]), with_existing=True) == []


def test_text_is_trimmed_and_a_blank_name_is_dropped():
    """A department named only spaces is not saved."""
    rows = _build(_answer([_dept("D1", "   "), _dept("D2", "  Finance  ")]))

    assert [r["title"] for r in rows] == ["Finance"]


# ----------------------------------------------------------------------- KPIs

def _kpi_rows(rows):
    return [r for r in rows if r["kind"] == "kpi"]


def test_weights_are_rescaled_to_exactly_the_budget():
    """Claude says 60 and 60 (120%): they become 50.00 and 50.00."""
    assert normalize_weights([60, 60], Decimal(100)) == [Decimal("50.00"), Decimal("50.00")]


def test_rounding_leftover_goes_on_the_first_weight_so_the_total_is_exact():
    """Three equal weights of 100: 33.33 + 33.33 + 33.33 = 99.99, the first gets the extra cent."""
    result = normalize_weights([1, 1, 1], Decimal(100))

    assert sum(result) == Decimal("100.00")
    assert result == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]


def test_zero_or_negative_weights_split_the_budget_equally_and_nan_counts_as_zero():
    """Nothing usable: equal shares. A budget below 100 (an existing department's room) is honoured."""
    assert normalize_weights([0, -5], Decimal(40)) == [Decimal("20.00"), Decimal("20.00")]
    assert normalize_weights([float("nan"), 30], Decimal(100)) == [Decimal("0.00"), Decimal("100.00")]


def test_kpis_for_a_new_department_get_weights_that_add_up_to_100():
    """Two KPIs for Operations, proposed as 90 and 90: saved as 50 and 50."""
    rows = _build(
        _answer(
            [_dept("D1", "Operations")],
            kpis=[
                _kpi("On-time delivery", "D1", 90, target_value=95, unit="%"),
                _kpi("Transit time", "D1", 90, target_value=2, unit="days", lower_is_better=True),
            ],
        )
    )

    kpis = _kpi_rows(rows)
    assert [(k["title"], k["kpi_weight"]) for k in kpis] == [
        ("On-time delivery", Decimal("50.00")), ("Transit time", Decimal("50.00")),
    ]
    assert kpis[0]["department_ref"] == "D1" and kpis[0]["department_id"] is None
    assert (kpis[0]["kpi_target_value"], kpis[0]["kpi_unit"], kpis[0]["kpi_is_inverse"]) == (
        Decimal("95.00"), "%", False,
    )
    assert kpis[1]["kpi_is_inverse"] is True


def test_a_kpi_can_point_at_a_key_result_that_was_kept():
    """K1 exists, so the link is kept; K9 does not, so that KPI is kept without a link."""
    objective = ProposedObjective(
        ref="O1", title="Deliver", department="D1", key_results=[_kr("K1", "95% on time")], rationale="r",
    )

    rows = _build(
        _answer(
            [_dept("D1", "Operations")],
            objectives=[objective],
            kpis=[_kpi("On time", "D1", 50, key_result="k1"), _kpi("Cost", "D1", 50, key_result="K9")],
        )
    )

    links = {k["title"]: k["key_result_ref"] for k in _kpi_rows(rows)}
    assert links == {"On time": "K1", "Cost": None}


def test_a_kpi_for_an_unknown_department_is_dropped():
    """'D9' was never proposed or shown."""
    rows = _build(_answer([_dept("D1", "Operations")], kpis=[_kpi("Ghost", "D9")]))

    assert _kpi_rows(rows) == []


def test_at_most_four_kpis_per_department_are_kept():
    """Six proposed for one department: the first four stay."""
    kpis = [_kpi("KPI " + str(n), "D1", 10) for n in range(6)]

    rows = _build(_answer([_dept("D1", "Operations")], kpis=kpis))

    assert [k["title"] for k in _kpi_rows(rows)] == ["KPI 0", "KPI 1", "KPI 2", "KPI 3"]


def test_an_existing_department_with_no_room_left_gets_no_kpis():
    """Sales already uses all 100% of its KPI weight: nothing more can be added."""
    rows = _build(
        _answer(kpis=[_kpi("Extra", "ED1")]), with_existing=True, kpi_room={SALES_ID: Decimal(0)}
    )

    assert _kpi_rows(rows) == []


def test_an_existing_department_with_some_room_gets_weights_that_fit_it():
    """Sales has 30% free: two KPIs share exactly 30%, so creating them cannot exceed 100."""
    rows = _build(
        _answer(kpis=[_kpi("A", "ED1", 70), _kpi("B", "ED1", 30)]),
        with_existing=True,
        kpi_room={SALES_ID: Decimal(30)},
    )

    kpis = _kpi_rows(rows)
    assert sum(k["kpi_weight"] for k in kpis) == Decimal("30.00")
    assert kpis[0]["department_id"] == SALES_ID


def test_a_target_that_cannot_fit_the_column_is_dropped_not_crashed_on():
    """1e15 would overflow a 14-digit column: saved as 'no target'."""
    rows = _build(_answer([_dept("D1", "Ops")], kpis=[_kpi("Huge", "D1", 100, target_value=1e15)]))

    assert _kpi_rows(rows)[0]["kpi_target_value"] is None


def test_the_same_ref_used_for_two_kinds_cannot_crash_the_save():
    """A department and a position both called 'P1': the second is dropped, not a crash.

    Refs are unique per batch in the database, so this has to be handled here.
    """
    rows = _build(
        _answer([_dept("P1", "Operations")], [_pos("P1", "Manager", "P1")])
    )

    assert [r["kind"] for r in rows] == ["department"]


def test_a_reused_key_result_ref_keeps_the_key_result_but_loses_its_ref():
    """Two objectives both use K1: the second K1 is still saved, without a ref."""
    first = ProposedObjective(ref="O1", title="One", department=None, key_results=[_kr("K1", "a")], rationale="r")
    second = ProposedObjective(ref="O2", title="Two", department=None, key_results=[_kr("K1", "b")], rationale="r")

    rows = _build(_answer(objectives=[first, second]))

    refs = [r["ref"] for r in rows if r["kind"] == "key_result"]
    assert refs == ["K1", None]
