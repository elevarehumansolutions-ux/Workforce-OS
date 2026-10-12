"""The period a task-count KPI is counted over: the organization's current fiscal quarter.

A KPI tracked by task count (``kpis.tracking_mode = 'task_count'``) shows how
many linked tasks were completed "this quarter". Quarters follow the
organization's fiscal year (``fiscal_year_start_month``) and are measured on
the organization's own clock (its timezone), the same way attendance days are.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.fiscal import get_fiscal_quarter_start


def current_fiscal_quarter(
    fiscal_year_start_month: int, timezone_name: str, now: datetime
) -> tuple[datetime, datetime]:
    """Work out the fiscal quarter that contains ``now``.

    Example: for a fiscal year starting in April, in Lagos, "now" being
    2 October 2026 gives a quarter from midnight on 1 October 2026 up to (but
    not including) midnight on 1 January 2027, both on Lagos time.

    Args:
        fiscal_year_start_month: The organization's fiscal year start month (1-12).
        timezone_name: The organization's IANA timezone, e.g. ``"Africa/Lagos"``.
        now: The current moment (any timezone).

    Returns:
        ``(start, end)``: the quarter starts at ``start`` and ends just before
        ``end``. Both are timezone-aware.
    """
    local_now = now.astimezone(ZoneInfo(timezone_name))
    start = get_fiscal_quarter_start(fiscal_year_start_month, local_now)
    return start, _three_months_after(start)


def _three_months_after(start: datetime) -> datetime:
    """The first moment of the month three months after ``start`` (a quarter's end)."""
    month = start.month + 3
    year = start.year
    if month > 12:
        month -= 12
        year += 1
    return datetime(year, month, 1, tzinfo=start.tzinfo)
