"""Request and response shapes for the Scoring module's read endpoints."""

import decimal
import uuid
from datetime import date

from pydantic import BaseModel


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
