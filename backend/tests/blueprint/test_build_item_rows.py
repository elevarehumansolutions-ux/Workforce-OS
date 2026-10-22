"""How Claude's answer is checked before anything is saved (pure: no database, no API).

Scenario: Kelechi runs a logistics company. Claude proposes a structure; the
code keeps what makes sense and drops what Claude invented or got wrong.
"""
import uuid

from app.modules.blueprint.generation import KnownStructure, build_item_rows
from app.modules.blueprint.schemas import (
    BlueprintAnswer,
    ProposedCleanup,
    ProposedDepartment,
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


def _answer(departments=(), positions=(), objectives=(), cleanups=()):
    return BlueprintAnswer(
        departments=list(departments),
        positions=list(positions),
        objectives=list(objectives),
        cleanups=list(cleanups),
    )


def _build(answer, *, with_existing=False, objective_titles=()):
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
        key_results=["a", "b", "c", "d", "e"], rationale="Core goal.",
    )

    rows = _build(_answer(objectives=[objective]))

    assert _kinds(rows) == ["objective"] + ["key_result"] * 4
    assert {r["objective_ref"] for r in rows[1:]} == {"O1"}


def test_an_objective_the_company_already_has_is_skipped():
    """'Grow Revenue' (any case) is already an OKR: not proposed again."""
    objective = ProposedObjective(
        ref="O1", title="grow  revenue", department=None, key_results=["x"], rationale="r",
    )

    rows = _build(_answer(objectives=[objective]), objective_titles=["grow revenue"])

    assert rows == []


def test_an_objective_for_an_unknown_department_is_dropped():
    """Better to lose it than to attach it to the wrong place or call it company-wide."""
    objective = ProposedObjective(
        ref="O1", title="Hit target", department="D5", key_results=["x"], rationale="r",
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
