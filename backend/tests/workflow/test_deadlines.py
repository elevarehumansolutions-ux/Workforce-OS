"""Tests for business-hours deadlines (M11 slice C).

All dates are October 2026: the 12th is a Monday, the 16th a Friday, the 17th a
Saturday. Times are written in Lagos time (UTC+1, no daylight saving).
"""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.workflow.deadlines import add_business_hours

LAGOS = ZoneInfo("Africa/Lagos")


def lagos(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment on the given October 2026 day, in Lagos time."""
    return datetime(2026, 10, day, hour, minute, tzinfo=LAGOS)


def deadline(start: datetime, hours: int) -> datetime:
    """The deadline in Lagos time, so expectations read like a wall clock."""
    return add_business_hours(start, hours, "Africa/Lagos").astimezone(LAGOS)


@pytest.mark.parametrize(
    ("start", "hours", "expected"),
    [
        # Inside one working day.
        (lagos(12, 10), 4, lagos(12, 14)),
        # Mon 14:00: 3h left Monday, 8 Tuesday, 8 Wednesday, 5 more Thursday.
        (lagos(12, 14), 24, lagos(15, 14)),
        # Lands exactly on closing time: stays at 17:00, not the next morning.
        (lagos(12, 9), 8, lagos(12, 17)),
        (lagos(12, 15), 2, lagos(12, 17)),
        # One minute too many spills into the next morning.
        (lagos(12, 15, 1), 2, lagos(13, 9, 1)),
    ],
)
def test_hours_are_counted_inside_the_working_day(start, hours, expected):
    """Only 09:00 to 17:00 on weekdays counts."""
    assert deadline(start, hours) == expected


@pytest.mark.parametrize(
    ("start", "hours", "expected"),
    [
        # Friday 17:00 is closing time: counting starts Monday 09:00. 24h = 3 days.
        (lagos(16, 17), 24, lagos(21, 17)),
        # Friday 14:00 + 8h: 3h Friday, 5h on Monday morning.
        (lagos(16, 14), 8, lagos(19, 14)),
        # Saturday and Sunday: nothing counts until Monday 09:00.
        (lagos(17, 12), 1, lagos(19, 10)),
        (lagos(18, 12), 1, lagos(19, 10)),
    ],
)
def test_nights_and_weekends_do_not_count(start, hours, expected):
    """A task created out of hours starts counting when the office opens."""
    assert deadline(start, hours) == expected


@pytest.mark.parametrize(
    ("start", "hours", "expected"),
    [
        (lagos(13, 7), 2, lagos(13, 11)),  # Tuesday 07:00, before opening
        (lagos(13, 20), 1, lagos(14, 10)),  # Tuesday 20:00, after closing
        (lagos(13, 9), 1, lagos(13, 10)),  # exactly at opening
    ],
)
def test_before_opening_and_after_closing_start_at_the_next_opening(start, hours, expected):
    """07:00 and 20:00 both count from the next 09:00."""
    assert deadline(start, hours) == expected


def test_a_long_turnaround_crosses_several_weekends():
    """80 business hours is ten full working days: two weeks, ending at close on a Friday."""
    assert deadline(lagos(12, 9), 80) == lagos(23, 17)


def test_the_organizations_timezone_decides_the_working_day_and_the_answer_is_utc():
    """16:00 UTC is 17:00 in Lagos (closing), so one hour later means Tuesday 10:00 Lagos = 09:00 UTC."""
    start = datetime(2026, 10, 12, 16, 0, tzinfo=UTC)

    result = add_business_hours(start, 1, "Africa/Lagos")

    assert result == datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    assert result.tzinfo == UTC


def test_a_start_in_another_timezone_is_converted_first():
    """The same instant in New York time gives the same deadline."""
    new_york = ZoneInfo("America/New_York")
    start = datetime(2026, 10, 12, 4, 0, tzinfo=new_york)  # 08:00 UTC, which is 09:00 in Lagos

    result = add_business_hours(start, 8, "Africa/Lagos")

    assert result.astimezone(LAGOS) == lagos(12, 17)
