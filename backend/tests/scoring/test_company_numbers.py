"""Tests for the pooled company numbers and the quarter step (M12 slice F part 1). Pure: no database."""
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationException
from app.modules.scoring.company import CompanyNumbers, check_custom_range, previous_quarter_dates, range_moments


def row(department_id, result, share, on_time=0, late=0, not_done=0):
    """A stand-in for one department's saved row."""
    return SimpleNamespace(
        department_id=department_id,
        kpi_results_score=None if result is None else Decimal(result),
        revenue_allocation_percentage=None if share is None else Decimal(share),
        punctuality_on_time=on_time,
        punctuality_late=late,
        punctuality_not_done=not_done,
    )


def test_the_previous_quarter_steps_back_three_months_and_across_a_year():
    """October-December is preceded by July-September; January-March by October-December of last year."""
    assert previous_quarter_dates(date(2026, 10, 1), date(2026, 12, 31)) == (date(2026, 7, 1), date(2026, 9, 30))
    assert previous_quarter_dates(date(2026, 1, 1), date(2026, 3, 31)) == (date(2025, 10, 1), date(2025, 12, 31))
    assert previous_quarter_dates(date(2026, 4, 1), date(2026, 6, 30)) == (date(2026, 1, 1), date(2026, 3, 31))


def test_a_custom_range_needs_both_dates_in_order_and_at_most_a_year():
    """Half a range, a backwards range and a two-year range are refused; a year is fine."""
    assert check_custom_range(date(2026, 1, 15), date(2026, 3, 20)) == (date(2026, 1, 15), date(2026, 3, 20))
    assert check_custom_range(date(2026, 1, 1), date(2026, 12, 31)) == (date(2026, 1, 1), date(2026, 12, 31))
    for first, last in [(None, date(2026, 3, 1)), (date(2026, 3, 1), None),
                        (date(2026, 3, 20), date(2026, 1, 15)), (date(2025, 1, 1), date(2026, 12, 31))]:
        with pytest.raises(ValidationException):
            check_custom_range(first, last)


def test_the_range_runs_from_midnight_to_midnight_on_the_companys_clock():
    """15 January to 20 March in Lagos (UTC+1): from 14 Jan 23:00 UTC up to 20 March 23:00 UTC."""
    start, end = range_moments(date(2026, 1, 15), date(2026, 3, 20), "Africa/Lagos")

    assert start.astimezone(UTC) == datetime(2026, 1, 14, 23, 0, tzinfo=UTC)
    assert end.astimezone(UTC) == datetime(2026, 3, 20, 23, 0, tzinfo=UTC)


def test_punctuality_pools_every_departments_tasks_instead_of_averaging_their_scores():
    """Sales 1 task on time; Operations 9 tasks, none done: pooled 10 tasks = 10, not the average of 100 and 0."""
    numbers = CompanyNumbers([row("sales", "70", "60", on_time=1), row("ops", "90", "40", not_done=9)])

    assert (numbers.on_time, numbers.late, numbers.not_done) == (1, 0, 9)
    assert numbers.punctuality_score == Decimal("10.00")


def test_the_headline_and_which_departments_it_counted():
    """HR has a result but no share, so it is not counted; Finance has a share but no result, so it is not either."""
    numbers = CompanyNumbers(
        [row("sales", "70", "60"), row("ops", "90", "30"), row("hr", "100", None), row("finance", None, "10")]
    )

    assert numbers.headline_score == Decimal("76.67")
    assert numbers.departments_counted == 2
    assert numbers.counted_department_ids == ["sales", "ops"]
    assert numbers.plain_average is False


def test_with_no_shares_every_department_that_has_a_result_is_counted():
    """The plain-average fallback counts everyone with a result."""
    numbers = CompanyNumbers([row("sales", "70", None), row("ops", "90", None), row("hr", None, None)])

    assert numbers.headline_score == Decimal("80.00")
    assert numbers.plain_average is True
    assert numbers.counted_department_ids == ["sales", "ops"]


def test_nothing_measured_is_no_data():
    """No results and no tasks: both numbers None."""
    numbers = CompanyNumbers([row("sales", None, "60")])

    assert numbers.headline_score is None and numbers.punctuality_score is None
    assert numbers.departments_counted == 0
