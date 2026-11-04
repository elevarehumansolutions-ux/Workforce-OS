"""The company-wide numbers, worked out from the departments' saved rows (M12 slice F).

Plain logic with no database, like ``marking.py`` and ``rollup.py``.
"""

from datetime import date, timedelta
from decimal import Decimal

from .marking import score_from_counts
from .rollup import company_headline


def previous_quarter_dates(first_day: date, last_day: date) -> tuple[date, date]:
    """The quarter before the one that starts on ``first_day`` (the 1st of a month).

    Example: 1 October to 31 December is preceded by 1 July to 30 September.
    ``last_day`` is not needed; it is kept so callers pass a whole period.
    """
    month = first_day.month - 3
    year = first_day.year
    if month < 1:
        month = month + 12
        year = year - 1
    return date(year, month, 1), first_day - timedelta(days=1)


class CompanyNumbers:
    """The two company numbers of one period and what they rest on.

    Attributes:
        headline_score: Departments' KPI results weighted by revenue share, or None.
        departments_counted: How many departments the headline counts.
        plain_average: True when no department had a share and a plain average was used.
        on_time, late, not_done: Every department's tasks pooled.
        punctuality_score: The pooled score, or None when there are no tasks.
        department_counts: Which department ids the headline counted.
    """

    def __init__(self, rows: list):
        """Work out the numbers from one period's department rows."""
        pairs = [(row.kpi_results_score, row.revenue_allocation_percentage) for row in rows]
        headline, counted, plain = company_headline(pairs)
        self.headline_score: Decimal | None = headline
        self.departments_counted = counted
        self.plain_average = plain

        self.on_time = sum(row.punctuality_on_time for row in rows)
        self.late = sum(row.punctuality_late for row in rows)
        self.not_done = sum(row.punctuality_not_done for row in rows)
        self.punctuality_score: Decimal | None = score_from_counts(self.on_time, self.late, self.not_done)

        self.counted_department_ids = []
        for row in rows:
            if row.kpi_results_score is None:
                continue
            if plain or row.revenue_allocation_percentage is not None:
                self.counted_department_ids.append(row.department_id)
