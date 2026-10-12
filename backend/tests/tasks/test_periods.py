"""Tests for the fiscal quarter a task-count KPI is counted over (M10 slice F). No database needed."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.tasks.periods import current_fiscal_quarter

LAGOS = "Africa/Lagos"


@pytest.mark.parametrize(
    "fiscal_start_month, now, expected_start, expected_end",
    [
        # January fiscal year: ordinary calendar quarters.
        (1, datetime(2026, 10, 2, 9, 0, tzinfo=UTC), (2026, 10, 1), (2027, 1, 1)),    # the year wraps
        (1, datetime(2026, 2, 14, 9, 0, tzinfo=UTC), (2026, 1, 1), (2026, 4, 1)),
        (1, datetime(2026, 3, 31, 9, 0, tzinfo=UTC), (2026, 1, 1), (2026, 4, 1)),     # last day of a quarter
        (1, datetime(2026, 4, 1, 9, 0, tzinfo=UTC), (2026, 4, 1), (2026, 7, 1)),      # first day of the next
        # April fiscal year: quarters begin in April, July, October, January.
        (4, datetime(2026, 10, 2, 9, 0, tzinfo=UTC), (2026, 10, 1), (2027, 1, 1)),
        (4, datetime(2026, 2, 14, 9, 0, tzinfo=UTC), (2026, 1, 1), (2026, 4, 1)),
        (4, datetime(2026, 5, 20, 9, 0, tzinfo=UTC), (2026, 4, 1), (2026, 7, 1)),
        # A fiscal year starting in November: quarters begin Nov, Feb, May, Aug.
        (11, datetime(2026, 12, 25, 9, 0, tzinfo=UTC), (2026, 11, 1), (2027, 2, 1)),
        (11, datetime(2026, 1, 10, 9, 0, tzinfo=UTC), (2025, 11, 1), (2026, 2, 1)),
    ],
)
def test_the_quarter_containing_now(fiscal_start_month, now, expected_start, expected_end):
    """The start is the first day of the fiscal quarter; the end is the first day of the next one."""
    start, end = current_fiscal_quarter(fiscal_start_month, LAGOS, now)

    assert (start.year, start.month, start.day) == expected_start
    assert (end.year, end.month, end.day) == expected_end
    assert (start.hour, start.minute) == (0, 0)


def test_the_quarter_is_measured_on_the_organizations_clock_not_utc():
    """23:30 UTC on 31 December is already 00:30 on 1 January in Lagos (UTC+1): a new quarter has begun there."""
    just_after_new_year_in_lagos = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)

    lagos_start, _ = current_fiscal_quarter(1, LAGOS, just_after_new_year_in_lagos)
    utc_start, _ = current_fiscal_quarter(1, "UTC", just_after_new_year_in_lagos)

    assert (lagos_start.year, lagos_start.month) == (2027, 1)
    assert (utc_start.year, utc_start.month) == (2026, 10)


def test_the_quarter_boundaries_are_timezone_aware_and_in_the_organizations_zone():
    """Comparing them with the database's timestamps must be unambiguous."""
    start, end = current_fiscal_quarter(1, LAGOS, datetime(2026, 5, 5, tzinfo=UTC))

    assert start.tzinfo is not None and end.tzinfo is not None
    assert start.utcoffset().total_seconds() == 3600       # Lagos is UTC+1 all year
    assert start == datetime(2026, 4, 1, tzinfo=ZoneInfo(LAGOS))
