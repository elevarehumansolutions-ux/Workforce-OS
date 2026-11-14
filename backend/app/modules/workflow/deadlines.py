"""Working out a step's deadline in business hours.

A step says "24 hours". Counting plain clock hours would make a task that
starts on Friday at 17:00 due on Saturday at 17:00, when nobody is at work.
So hours are counted only inside the company's working week, in the
organization's own timezone.

The working week is a company setting: a start hour, an end hour and the
working days (08_DECISIONS.md 2026-11-14). A company that never sets it gets
the default, Monday to Friday 09:00 to 17:00 (8 hours a day). Public holidays
and lunch or break times are NOT skipped; they are left for later and only
this file would change.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


class WorkingWeek:
    """When a company is at work: which weekdays, and from which hour to which hour.

    ``days`` are weekday numbers with Monday as 0 and Sunday as 6 (the numbers Python uses).
    Hours are whole hours, 0 to 23.
    """

    def __init__(self, start_hour: int = 9, end_hour: int = 17, days: tuple = (0, 1, 2, 3, 4)):
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.days = list(days)

    def hours_per_day(self) -> int:
        """How long one working day is. A step measured in "days" is this many hours per day."""
        return self.end_hour - self.start_hour


DEFAULT_WEEK = WorkingWeek()


def _at_hour(moment: datetime, hour: int) -> datetime:
    """The same day as ``moment``, at ``hour`` o'clock sharp."""
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def _next_working_moment(moment: datetime, week: WorkingWeek) -> datetime:
    """The first moment at or after ``moment`` when the office is open.

    Examples with the default week: Tuesday 07:00 -> Tuesday 09:00. Tuesday 12:00 -> Tuesday 12:00.
    Tuesday 17:00 (closing time) -> Wednesday 09:00. Saturday 12:00 -> Monday 09:00.
    """
    is_workday = moment.weekday() in week.days
    if is_workday and moment < _at_hour(moment, week.start_hour):
        return _at_hour(moment, week.start_hour)
    if is_workday and moment < _at_hour(moment, week.end_hour):
        return moment

    day = _at_hour(moment, week.start_hour) + timedelta(days=1)
    while day.weekday() not in week.days:  # skip the days the company does not work
        day += timedelta(days=1)
    return day


def add_business_hours(start: datetime, hours: int, timezone_name: str, week: WorkingWeek = DEFAULT_WEEK) -> datetime:
    """The moment ``hours`` business hours after ``start``.

    Example (timezone Africa/Lagos, default week): Monday 14:00 plus 24 hours. Monday has 3
    hours left, Tuesday and Wednesday 8 each (19 used), so the last 5 hours
    fall on Thursday morning: Thursday 14:00. A deadline that lands exactly on
    closing time stays at the closing hour that day (it does not slide to the next
    morning).

    Args:
        start: When the clock starts (any timezone, e.g. the task's creation time).
        hours: Business hours allowed, a whole number above 0.
        timezone_name: The organization's timezone, e.g. ``Africa/Lagos``.
        week: The company's working week; the default is Monday to Friday, 09:00 to 17:00.

    Returns:
        The deadline, in UTC.
    """
    current = _next_working_moment(start.astimezone(ZoneInfo(timezone_name)), week)
    remaining = timedelta(hours=hours)

    while True:
        closing_time = _at_hour(current, week.end_hour)
        left_today = closing_time - current
        if remaining <= left_today:
            return (current + remaining).astimezone(UTC)
        remaining -= left_today
        current = _next_working_moment(closing_time, week)
