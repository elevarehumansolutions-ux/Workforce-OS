"""Request and response shapes for the Scoring module's read endpoints."""

import decimal
import uuid
from datetime import date

from pydantic import BaseModel

from app.core.schemas import PaginationMeta


class KPIScoreLine(BaseModel):
    """One person's result on one KPI.

    ``score_percentage`` is empty when the person had no valid tasks on this
    KPI: that means "no data", it is never shown as 0.
    """

    kpi_id: uuid.UUID
    kpi_name: str
    weight: decimal.Decimal
    score_percentage: decimal.Decimal | None
    tasks_on_time: int
    tasks_late: int
    tasks_not_done: int


class PersonScoreLine(BaseModel):
    """One person in a department's list: their overall score and how many KPIs it rests on.

    ``overall_score`` is empty when the person has no scored tasks in the period
    (no data, never 0).
    """

    employee_id: uuid.UUID
    employee_name: str
    overall_score: decimal.Decimal | None
    kpis_counted: int
    kpis_expected: int


class DepartmentPerformanceResponse(BaseModel):
    """A department's performance for one period: two numbers side by side, then its people.

    The two numbers are never blended (08_DECISIONS.md 2026-10-21, question 5):

    - ``kpi_results_score``: did the department hit its goals? It can be above
      100. ``kpis_counted`` of ``kpis_expected`` is the "N of M" beside it.
    - ``punctuality_score``: do people deliver on time, over every task of the
      department, including tasks nobody holds. The three counts sit beside it.

    Either score is ``null`` when there is no data, with its own reason. ``people``
    is one page of the department's people, highest overall score first, people
    with no data last.
    """

    department_id: uuid.UUID
    department_name: str
    period_start: date
    period_end: date
    is_final: bool
    kpi_results_score: decimal.Decimal | None
    kpis_counted: int
    kpis_expected: int
    kpi_results_no_data_reason: str | None
    punctuality_score: decimal.Decimal | None
    punctuality_on_time: int
    punctuality_late: int
    punctuality_not_done: int
    punctuality_no_data_reason: str | None
    people: list[PersonScoreLine]
    people_pagination: PaginationMeta


class LeaderboardEntry(BaseModel):
    """One ranked person.

    ``valid_tasks`` and ``kpis_counted`` of ``kpis_expected`` are shown beside
    the score so a 100 on one task reads differently from a 95 on twenty.
    Equal scores share a rank (1, 2, 2, 4).
    """

    rank: int
    employee_id: uuid.UUID
    employee_name: str
    department_id: uuid.UUID
    department_name: str
    overall_score: decimal.Decimal
    valid_tasks: int
    kpis_counted: int
    kpis_expected: int


class LeaderboardResponse(BaseModel):
    """One page of the ranked people. People with no data are not ranked, so not listed."""

    period_start: date
    period_end: date
    is_final: bool
    entries: list[LeaderboardEntry]
    pagination: PaginationMeta


class PersonPerformanceResponse(BaseModel):
    """A person's performance card for one period.

    Example: Chidi, 1 July to 30 September. Lead Follow-up 83 (weight 70),
    Contract Paperwork 60 (weight 30), overall 75.4, "2 of 2 KPIs counted".

    ``overall_score`` is the weighted average of the KPIs that have a score and
    is empty when none has one (``no_data_reason`` then says why).
    ``is_final`` is true once the period has closed and its numbers are frozen.
    """

    employee_id: uuid.UUID
    employee_name: str
    department_id: uuid.UUID | None
    period_start: date
    period_end: date
    is_final: bool
    overall_score: decimal.Decimal | None
    kpis_counted: int
    kpis_expected: int
    no_data_reason: str | None
    kpis: list[KPIScoreLine]
