"""Tests for the executive summary's fact sheet, number check and plain fallback (M12 slice G). Pure."""
from decimal import Decimal

from app.modules.scoring.summary_facts import (
    build_fact_sheet,
    change,
    fingerprint,
    number,
    plain_summary,
    unsupported_numbers,
)


def sheet(closed=False):
    """The Sales / Operations example: company 79 (+5), punctuality 81 (-2)."""
    company = {
        "headline": 79, "headline_change": 5, "departments_counted": 2, "departments_total": 3,
        "punctuality": 81, "punctuality_change": -2, "tasks_on_time": 40, "tasks_late": 8, "tasks_not_done": 2,
    }
    departments = [
        {"name": "Sales", "goals_score": 70, "goals_change": -5, "punctuality": 86, "punctuality_change": 3},
        {"name": "Operations", "goals_score": 90, "goals_change": 12.5, "punctuality": 88, "punctuality_change": None},
    ]
    delays = [{"department": "Finance", "reason": "awaiting_approval", "held_back_tasks": 4}]
    return build_fact_sheet(closed, company, departments, delays)


def test_scores_are_shown_to_one_decimal_without_a_pointless_dot_zero():
    """66.67 becomes 66.7, 79.00 becomes 79, and a missing score stays missing."""
    assert number(Decimal("66.67")) == 66.7
    assert number(Decimal("79.00")) == 79
    assert number(None) is None


def test_a_change_is_points_gained_or_lost_and_needs_both_periods():
    """70 now against 75 before is -5; with no earlier figure there is no change."""
    assert change(Decimal("70"), Decimal("75")) == -5
    assert change(Decimal("90"), Decimal("77.5")) == 12.5
    assert change(Decimal("70"), None) is None
    assert change(None, Decimal("70")) is None


def test_the_sheet_says_so_for_a_running_and_a_closed_quarter_and_holds_no_dates():
    """'so far' while open, 'ended' when closed; nothing in it for the model to turn into a date."""
    assert sheet(closed=False)["period"] == "the quarter so far"
    assert sheet(closed=True)["period"] == "the quarter that has ended"


def test_numbers_that_are_in_the_facts_pass():
    """79, 5, 81, 2, 12.5 and '70%' are all facts; a drop of -5 may be written as 'down 5'."""
    text = "The company scored 79%, up 5 points. Punctuality is 81, down 2. Sales is at 70, down 5. Operations rose 12.5."

    assert unsupported_numbers(text, sheet()) == []


def test_a_number_that_is_not_in_the_facts_is_caught():
    """The model says 19 points when the data says 12.5; and a sum it worked out itself (50 tasks) is not a fact."""
    wrong = unsupported_numbers("Operations rose 19 points, across 50 tasks.", sheet())

    assert wrong == ["19", "50"]


def test_formats_do_not_matter_but_digits_inside_words_and_codes_are_ignored():
    """79.0 equals 79; 'Q3' is not the number 3; a department name's own digit is allowed."""
    with_digit_in_name = sheet()
    with_digit_in_name["departments"][0]["name"] = "Unit 7"

    assert unsupported_numbers("Score 79.0 in Q3.", sheet()) == []
    assert unsupported_numbers("Unit 7 is at 70.", with_digit_in_name) == []
    assert unsupported_numbers("Unit 9 is at 70.", with_digit_in_name) == ["9"]


def test_the_fingerprint_changes_only_when_the_facts_change():
    """Same facts, same hash; one point different, a different hash."""
    changed = sheet()
    changed["company"]["headline"] = 80

    assert fingerprint(sheet()) == fingerprint(sheet())
    assert fingerprint(sheet()) != fingerprint(changed)


def test_the_plain_fallback_states_only_facts_and_passes_its_own_check():
    """No model wording; every number in it is in the sheet."""
    text = plain_summary(sheet())

    assert text == (
        "Company score 79 (+5); punctuality 81 (-2). "
        "Sales: goals 70 (-5), punctuality 86 (+3). "
        "Operations: goals 90 (+12.5), punctuality 88."
    )
    assert unsupported_numbers(text, sheet()) == []
