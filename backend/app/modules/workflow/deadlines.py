"""Working out a step's deadline in business hours.

A step says "24 hours". Counting plain clock hours would make a task that
starts on Friday at 17:00 due on Saturday at 17:00, when nobody is at work.
So hours are counted only inside the working week: Monday to Friday,
09:00 to 17:00 (8 hours a day) in the organization's own timezone. Public
holidays are not skipped, and the working week is a constant here, not a
setting (08_DECISIONS.md 2026-10-12; configurable calendars are left for
later, and only this file would change).
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

WORKDAY_START_HOUR = 9
WORKDAY_END_HOUR = 17


def _at_hour(moment: datetime, hour: int) -> datetime:
    """The same day as ``moment``, at ``hour`` o'clock sharp."""
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def _next_working_moment(moment: datetime) -> datetime:
    """The first moment at or after ``moment`` when the office is open.

    Examples: Tuesday 07:00 -> Tuesday 09:00. Tuesday 12:00 -> Tuesday 12:00.
    Tuesday 17:00 (closing time) -> Wednesday 09:00. Saturday 12:00 -> Monday 09:00.
    """
    is_weekday = moment.weekday() < 5  # Monday is 0, Friday is 4
    if is_weekday and moment < _at_hour(moment, WORKDAY_START_HOUR):
        return _at_hour(moment, WORKDAY_START_HOUR)
    if is_weekday and moment < _at_hour(moment, WORKDAY_END_HOUR):
        return moment

    day = _at_hour(moment, WORKDAY_START_HOUR) + timedelta(days=1)
    while day.weekday() >= 5:  # skip Saturday and Sunday
        day += timedelta(days=1)
    return day


def add_business_hours(start: datetime, hours: int, timezone_name: str) -> datetime:
    """The moment ``hours`` business hours after ``start``.

    Example (timezone Africa/Lagos): Monday 14:00 plus 24 hours. Monday has 3
    hours left, Tuesday and Wednesday 8 each (19 used), so the last 5 hours
    fall on Thursday morning: Thursday 14:00. A deadline that lands exactly on
    closing time stays at 17:00 that day (it does not slide to the next
    morning).

    Args:
        start: When the clock starts (any timezone, e.g. the task's creation time).
        hours: Business hours allowed, a whole number above 0.
        timezone_name: The organization's timezone, e.g. ``Africa/Lagos``.

    Returns:
        The deadline, in UTC.
    """
    current = _next_working_moment(start.astimezone(ZoneInfo(timezone_name)))
    remaining = timedelta(hours=hours)

    while True:
        closing_time = _at_hour(current, WORKDAY_END_HOUR)
        left_today = closing_time - current
        if remaining <= left_today:
            return (current + remaining).astimezone(UTC)
        remaining -= left_today
        current = _next_working_moment(closing_time)
