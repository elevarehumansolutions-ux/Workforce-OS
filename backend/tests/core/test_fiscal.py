"""Tests for get_fiscal_quarter_start.

Covers the calendar-aligned case (fiscal_year_start_month=1, where quarter
math never wraps a calendar-year boundary) and the wraparound case
(fiscal_year_start_month=11, where one quarter — Nov/Dec/Jan — spans two
calendar years), since the wraparound is the part most likely to be
subtly wrong and isn't obvious from a read-through.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.core.fiscal import get_fiscal_quarter_start, is_due_for_quarterly_review


@pytest.mark.parametrize(
    "reference, expected",
    [
        # fiscal_year_start_month=1: quarters are the plain calendar quarters.
        (datetime(2026, 2, 15, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
        (datetime(2026, 5, 20, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)),
        (datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 7, 1, tzinfo=UTC)),
        (datetime(2026, 12, 31, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),
        # Exactly on a quarter boundary.
        (datetime(2026, 4, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)),
    ],
)
def test_calendar_aligned_fiscal_year(reference, expected):
    """fiscal_year_start_month=1 behaves like plain calendar quarters."""
    assert get_fiscal_quarter_start(1, reference) == expected


@pytest.mark.parametrize(
    "reference, expected",
    [
        # fiscal_year_start_month=11: quarters are Nov-Jan, Feb-Apr, May-Jul, Aug-Oct.
        # Nov/Dec themselves: quarter start is the same calendar year.
        (datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)),
        (datetime(2026, 12, 25, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)),
        # January: still the Nov-Jan quarter, but the quarter started in the
        # *previous* calendar year — the case the year-rollback logic exists for.
        (datetime(2027, 1, 15, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)),
        # The next quarter (Feb-Apr) resets back to the same calendar year.
        (datetime(2027, 3, 1, tzinfo=UTC), datetime(2027, 2, 1, tzinfo=UTC)),
    ],
)
def test_wraparound_fiscal_year(reference, expected):
    """fiscal_year_start_month=11 correctly rolls the year back for the Nov-Jan quarter."""
    assert get_fiscal_quarter_start(11, reference) == expected


def test_preserves_reference_timezone():
    """The returned timestamp carries the same tzinfo as the input, not a naive one."""
    reference = datetime(2026, 6, 1, tzinfo=UTC)
    result = get_fiscal_quarter_start(4, reference)
    assert result.tzinfo == UTC


class TestIsDueForQuarterlyReview:
    """is_due_for_quarterly_review: the Beat job's "did this org just turn over" check.

    Scenario: the Beat job runs daily with a 26-hour lookback. An org whose
    fiscal quarter started this morning is due; one whose quarter started
    two months ago is not — even though both are, technically, "this
    quarter" from get_fiscal_quarter_start's point of view.
    """

    def test_a_quarter_that_just_started_is_due(self):
        """6am on quarter-start day: well within a 26h lookback."""
        now = datetime(2026, 4, 1, 6, 0, tzinfo=UTC)
        assert is_due_for_quarterly_review(1, now, timedelta(hours=26)) is True

    def test_a_quarter_that_started_long_ago_is_not_due(self):
        """Mid-quarter: nowhere near the last boundary."""
        now = datetime(2026, 5, 15, tzinfo=UTC)
        assert is_due_for_quarterly_review(1, now, timedelta(hours=26)) is False

    def test_just_outside_the_lookback_window_is_not_due(self):
        """27 hours after a quarter starting exactly at midnight, with a 26h lookback."""
        now = datetime(2026, 4, 2, 3, 0, tzinfo=UTC)
        assert is_due_for_quarterly_review(1, now, timedelta(hours=26)) is False

    def test_the_wraparound_fiscal_year_is_still_handled_correctly(self):
        """Nov-start fiscal year: the Nov-Jan quarter turns over on Nov 1, not Jan 1."""
        just_after_november_start = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
        well_into_january = datetime(2027, 1, 15, tzinfo=UTC)

        assert is_due_for_quarterly_review(11, just_after_november_start, timedelta(hours=26)) is True
        assert is_due_for_quarterly_review(11, well_into_january, timedelta(hours=26)) is False
