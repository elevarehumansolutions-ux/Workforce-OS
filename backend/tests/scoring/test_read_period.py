"""Tests for which period a performance read is about (M12 slice E)."""
from datetime import UTC, date, datetime

import pytest

from app.core.exceptions import ValidationException
from app.modules.scoring.reads import resolve_period

THIRD_OF_OCTOBER = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


def test_no_dates_means_the_current_fiscal_quarter():
    """On 3 October a January-year company is in Q4: 1 October to 31 December."""
    assert resolve_period(1, "Africa/Lagos", THIRD_OF_OCTOBER, None, None) == (date(2026, 10, 1), date(2026, 12, 31))


def test_no_dates_follows_the_companys_own_fiscal_year():
    """For a company whose fiscal year starts in November, 3 October is in the quarter that began on 1 August."""
    assert resolve_period(11, "Africa/Lagos", THIRD_OF_OCTOBER, None, None) == (date(2026, 8, 1), date(2026, 10, 31))


def test_two_dates_are_used_exactly_as_given():
    """Last quarter, asked for by its dates, comes back unchanged."""
    asked = resolve_period(1, "Africa/Lagos", THIRD_OF_OCTOBER, date(2026, 7, 1), date(2026, 9, 30))
    assert asked == (date(2026, 7, 1), date(2026, 9, 30))


def test_only_one_date_is_refused():
    """A screen that sends half a range has a bug; say so."""
    with pytest.raises(ValidationException):
        resolve_period(1, "Africa/Lagos", THIRD_OF_OCTOBER, date(2026, 7, 1), None)
    with pytest.raises(ValidationException):
        resolve_period(1, "Africa/Lagos", THIRD_OF_OCTOBER, None, date(2026, 9, 30))


def test_an_end_before_the_start_is_refused():
    """30 September to 1 July is not a period."""
    with pytest.raises(ValidationException):
        resolve_period(1, "Africa/Lagos", THIRD_OF_OCTOBER, date(2026, 9, 30), date(2026, 7, 1))
