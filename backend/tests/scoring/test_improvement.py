"""Tests for the Most Improved rule (M12 slice F part 2). Pure: no database."""
from decimal import Decimal

from app.modules.scoring.improvement import Candidate, most_improved


def person(key, before, before_tasks, now, now_tasks):
    """A candidate with scores given as text (None = no data)."""
    return Candidate(
        key,
        None if before is None else Decimal(before),
        before_tasks,
        None if now is None else Decimal(now),
        now_tasks,
    )


def keys(candidates):
    """Just the keys, in order."""
    return [c.key for c in candidates]


def test_the_biggest_gain_in_points_comes_first():
    """Ada 40 to 70 (+30) is ahead of Dayo 60 to 65 (+5)."""
    listed = most_improved([person("dayo", "60", 12, "65", 12), person("ada", "40", 20, "70", 20)])

    assert keys(listed) == ["ada", "dayo"]
    assert listed[0].change_in_points() == Decimal("30")


def test_a_person_needs_ten_valid_tasks_in_both_periods():
    """Fewer than 10 in either period: not listed, however big the jump (a 5-task jump is luck)."""
    listed = most_improved([
        person("few_before", "0", 9, "100", 30),
        person("few_now", "0", 30, "100", 9),
        person("exactly_ten", "50", 10, "60", 10),
    ])

    assert keys(listed) == ["exactly_ten"]


def test_no_data_in_either_period_is_not_listed():
    """A missing score is not a zero to improve from."""
    assert most_improved([person("new", None, 0, "80", 20), person("gone", "80", 20, None, 0)]) == []


def test_only_real_improvements_are_listed():
    """No change and a drop are not 'most improved'."""
    assert most_improved([person("same", "70", 20, "70", 20), person("down", "80", 20, "60", 20)]) == []


def test_a_tie_goes_to_the_one_with_more_current_tasks():
    """Both +10: the one with 40 tasks behind it is listed first."""
    listed = most_improved([person("small", "50", 10, "60", 10), person("big", "50", 40, "60", 40)])

    assert keys(listed) == ["big", "small"]
