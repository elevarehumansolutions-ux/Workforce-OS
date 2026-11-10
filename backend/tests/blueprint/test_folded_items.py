"""The lean structure: what the plan leaves out because another department or role covers it.

Scenario: Kelechi runs a small logistics company. Claude proposes a Recruitment
department and says "Talent Sourcing" does not need to stand alone. The code keeps
that note only when what it points at really exists.
"""
import uuid

from app.modules.blueprint.generation import KnownStructure, build_item_rows
from app.modules.blueprint.prompts import MAX_FOLDED
from app.modules.blueprint.schemas import (
    BlueprintAnswer,
    ProposedDepartment,
    ProposedFold,
    ProposedPosition,
)

ORG = uuid.uuid4()
BATCH = uuid.uuid4()
SALES_ID = uuid.uuid4()
GM_ID = uuid.uuid4()


def _dept(ref, name):
    return ProposedDepartment(ref=ref, name=name, rationale="Needed.")


def _pos(ref, title, department):
    return ProposedPosition(ref=ref, title=title, department=department, rationale="Needed.")


def _fold(kind, name, covered_by):
    return ProposedFold(kind=kind, name=name, covered_by=covered_by, reason="One team can do both.")


def _build(departments=(), positions=(), folded=(), with_existing=False):
    """Run build_item_rows; ``with_existing`` gives the company a 'Sales' dept and a 'General Manager'."""
    answer = BlueprintAnswer(
        departments=list(departments),
        positions=list(positions),
        objectives=[],
        kpis=[],
        cleanups=[],
        folded=list(folded),
    )
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
        existing_objective_titles=set(),
    )


def _folded_rows(rows):
    return [row for row in rows if row["kind"] == "folded"]


def test_a_department_folded_into_a_proposed_one_points_at_it_by_ref():
    """Talent Sourcing is covered by D1 (Recruitment): it is saved as a note pointing at D1."""
    rows = _build(
        departments=[_dept("D1", "Recruitment")],
        folded=[_fold("department", "Talent Sourcing", "D1")],
    )

    note = _folded_rows(rows)[0]
    assert (note["title"], note["folded_into_ref"], note["rationale"]) == (
        "Talent Sourcing", "D1", "One team can do both.",
    )
    assert note.get("department_id") is None


def test_a_department_folded_into_one_the_company_already_has_points_at_the_real_row():
    """Sales (ED1) already exists, so the note carries its real id and no ref."""
    rows = _build(folded=[_fold("department", "Business Development", "ED1")], with_existing=True)

    note = _folded_rows(rows)[0]
    assert (note["department_id"], note["folded_into_ref"]) == (SALES_ID, None)


def test_a_role_folded_into_a_combined_role_points_at_the_position():
    """'HR Officer' is covered by P1, the combined 'HR and Talent Acquisition Officer'."""
    rows = _build(
        departments=[_dept("D1", "People")],
        positions=[_pos("P1", "HR and Talent Acquisition Officer", "D1")],
        folded=[_fold("position", "Talent Acquisition Officer", "P1")],
    )

    note = _folded_rows(rows)[0]
    assert (note["title"], note["folded_into_ref"]) == ("Talent Acquisition Officer", "P1")


def test_a_fold_that_points_at_nothing_real_is_dropped():
    """Claude says D9 covers it, but there is no D9: the note is not saved."""
    rows = _build(
        departments=[_dept("D1", "Recruitment")],
        folded=[_fold("department", "Talent Sourcing", "D9")],
    )

    assert _folded_rows(rows) == []


def test_a_department_label_cannot_cover_a_position():
    """A position fold must name a position; naming a department label is refused."""
    rows = _build(
        departments=[_dept("D1", "People")],
        folded=[_fold("position", "Recruiter", "D1")],
    )

    assert _folded_rows(rows) == []


def test_something_the_plan_does_keep_cannot_also_be_left_out():
    """Recruitment is proposed, so 'Recruitment folded into D2' contradicts the plan."""
    rows = _build(
        departments=[_dept("D1", "Recruitment"), _dept("D2", "People")],
        folded=[_fold("department", "recruitment", "D2")],
    )

    assert _folded_rows(rows) == []


def test_the_same_thing_is_not_left_out_twice():
    """Two notes for 'Talent Sourcing' collapse into one."""
    rows = _build(
        departments=[_dept("D1", "Recruitment")],
        folded=[
            _fold("department", "Talent Sourcing", "D1"),
            _fold("department", "talent sourcing", "D1"),
        ],
    )

    assert len(_folded_rows(rows)) == 1


def test_at_most_the_cap_of_folded_notes_are_kept():
    """Claude cannot fold the whole company away: only the first MAX_FOLDED notes survive."""
    notes = [_fold("department", f"Small Team {n}", "D1") for n in range(MAX_FOLDED + 5)]
    rows = _build(departments=[_dept("D1", "Operations")], folded=notes)

    assert len(_folded_rows(rows)) == MAX_FOLDED
