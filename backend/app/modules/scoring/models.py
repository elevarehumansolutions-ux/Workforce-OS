"""ORM models for the Scoring module (04_DATABASE.md Cluster 5).

Contains :class:`EmployeeKPIScore` (one person's score on one KPI for one
period), :class:`DepartmentScore` (one department's saved result for a period)
and :class:`ExecutiveSummary` (the short written summary of a period).

None of the three has ``deleted_at``: a closed period is permanent history.
While a period is still open its rows are refreshed every night; once
``finalized_at`` is set a row is frozen and is never written again
(08_DECISIONS.md 2026-10-21, question 4). There are no ORM relationships,
deliberately: the services do their own lookups, which avoids lazy-load
surprises under the async session (same choice as the Task and Workflow
modules).
"""

from __future__ import annotations

import decimal
import uuid
from datetime import date, datetime

from sqlalchemy import (
    DECIMAL,
    UUID,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel
from .enums import SummarySource


class EmployeeKPIScore(BaseModel):
    """One person's score on one KPI for one period.

    Example: Chidi's "Lead Follow-up" score for Q3 (1 July to 30 September).
    Each valid task earns 100 if done on time, 50 if done late and 0 if never
    done; the score is the average. The three counts are stored next to the
    score so the 100 / 50 / 0 values can be tuned later without losing what
    actually happened.

    ``score_percentage`` is empty exactly when the person had no valid tasks
    on this KPI: "no data" is never stored as 0 (enforced by a CHECK).
    ``weight_used`` is the KPI's weight when the row was last written, kept so
    a person's overall score for a closed period can be worked out from saved
    rows alone, even if HR edits the weights afterwards.
    Organization-scoped (RLS). See 08_DECISIONS.md 2026-10-21.
    """

    __tablename__ = "employee_kpi_scores"

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "kpi_id",
            "period_start",
            "period_end",
            name="uq_employee_kpi_scores_one_per_period",
        ),
        CheckConstraint("period_end >= period_start", name="check_employee_kpi_score_period_order"),
        CheckConstraint(
            "tasks_on_time >= 0 AND tasks_late >= 0 AND tasks_not_done >= 0",
            name="check_employee_kpi_score_counts_not_negative",
        ),
        CheckConstraint(
            "score_percentage IS NULL OR (score_percentage >= 0 AND score_percentage <= 100)",
            name="check_employee_kpi_score_range",
        ),
        CheckConstraint(
            "(tasks_on_time + tasks_late + tasks_not_done = 0 AND score_percentage IS NULL)"
            " OR (tasks_on_time + tasks_late + tasks_not_done > 0 AND score_percentage IS NOT NULL)",
            name="check_employee_kpi_score_null_only_when_no_tasks",
        ),
        CheckConstraint(
            "weight_used >= 0 AND weight_used <= 100",
            name="check_employee_kpi_score_weight_range",
        ),
        Index("idx_employee_kpi_scores_period", "organization_id", "period_start", "period_end"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this score belongs to",
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
        doc="The person scored",
    )

    kpi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kpis.id"),
        nullable=False,
        index=True,
        doc="The KPI the scored tasks are linked to",
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False, doc="First day of the period")

    period_end: Mapped[date] = mapped_column(Date, nullable=False, doc="Last day of the period")

    tasks_on_time: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Valid tasks done on time (100 each)"
    )

    tasks_late: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Valid tasks done late (50 each)"
    )

    tasks_not_done: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Valid tasks never done (0 each)"
    )

    score_percentage: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        doc="Average of the task marks, 0-100; empty = no valid tasks (no data), never 0",
    )

    weight_used: Mapped[decimal.Decimal] = mapped_column(
        DECIMAL(5, 2),
        nullable=False,
        doc="The KPI's weight (0-100) when this row was last written; frozen with the row",
    )

    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the period closed and this row was frozen; empty = still a running figure",
    )


class DepartmentScore(BaseModel):
    """One department's saved result for one period.

    A department shows TWO numbers side by side and never blended
    (08_DECISIONS.md 2026-10-21, question 5):

    - ``kpi_results_score``: "did the department hit its goals?", its KPI
      results against their targets, weighted. It can go above 100 (a team that
      exceeded its target). Example: 14 deals closed against a target of 20 is 70.
    - ``punctuality_score``: "do people deliver on time?", the 100 / 50 / 0
      marking averaged over ALL the department's tasks whose real deadline is in
      the period, including tasks nobody holds. Example: 86.

    ``kpis_counted`` out of ``kpis_expected`` is the "N of M" shown beside the
    headline. ``revenue_allocation_percentage`` is the department's revenue share
    when the row was last written, kept so the company score of a closed period
    never changes if HR edits the shares later.
    Organization-scoped (RLS). See 08_DECISIONS.md 2026-10-21.
    """

    __tablename__ = "department_scores"

    __table_args__ = (
        UniqueConstraint(
            "department_id",
            "period_start",
            "period_end",
            name="uq_department_scores_one_per_period",
        ),
        CheckConstraint("period_end >= period_start", name="check_department_score_period_order"),
        CheckConstraint(
            "kpis_counted >= 0 AND kpis_expected >= 0"
            " AND punctuality_on_time >= 0 AND punctuality_late >= 0 AND punctuality_not_done >= 0",
            name="check_department_score_counts_not_negative",
        ),
        CheckConstraint(
            "kpis_counted <= kpis_expected",
            name="check_department_score_counted_within_expected",
        ),
        CheckConstraint(
            "(kpis_counted = 0 AND kpi_results_score IS NULL)"
            " OR (kpis_counted > 0 AND kpi_results_score IS NOT NULL)",
            name="check_department_score_results_null_only_when_no_kpis",
        ),
        CheckConstraint(
            "kpi_results_score IS NULL OR kpi_results_score >= 0",
            name="check_department_score_results_not_negative",
        ),
        CheckConstraint(
            "(punctuality_on_time + punctuality_late + punctuality_not_done = 0"
            " AND punctuality_score IS NULL)"
            " OR (punctuality_on_time + punctuality_late + punctuality_not_done > 0"
            " AND punctuality_score IS NOT NULL)",
            name="check_department_score_punctuality_null_only_when_no_tasks",
        ),
        CheckConstraint(
            "punctuality_score IS NULL OR (punctuality_score >= 0 AND punctuality_score <= 100)",
            name="check_department_score_punctuality_range",
        ),
        CheckConstraint(
            "revenue_allocation_percentage IS NULL"
            " OR (revenue_allocation_percentage >= 0 AND revenue_allocation_percentage <= 100)",
            name="check_department_score_allocation_range",
        ),
        Index("idx_department_scores_period", "organization_id", "period_start", "period_end"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this score belongs to",
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
        doc="The department scored",
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False, doc="First day of the period")

    period_end: Mapped[date] = mapped_column(Date, nullable=False, doc="Last day of the period")

    kpi_results_score: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(6, 2),
        nullable=True,
        doc="Weighted KPI results against target (may exceed 100); empty = no KPI had a result (no data)",
    )

    kpis_counted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="KPIs that had a result (the N of 'N of M')"
    )

    kpis_expected: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="KPIs the department has (the M of 'N of M')"
    )

    punctuality_on_time: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Tasks done on time (assigned or not)"
    )

    punctuality_late: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Tasks done late"
    )

    punctuality_not_done: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Tasks never done, including tasks nobody holds"
    )

    punctuality_score: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        doc="Team punctuality, 0-100; empty = no valid tasks (no data), never 0",
    )

    revenue_allocation_percentage: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(6, 2),
        nullable=True,
        doc="The department's revenue share when this row was last written; frozen with the row",
    )

    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the period closed and this row was frozen; empty = still a running figure",
    )


class ExecutiveSummary(BaseModel):
    """The short written summary of one organization's period.

    Example: "Sales missed its target by 30% while the team stayed punctual at
    86%. Most delays came from approvals waiting on Finance." It never names an
    individual employee, and the model is never given names.

    There is ONE row per organization per period. While the period is open the
    weekly job replaces ``summary_text`` (and skips the week when
    ``facts_fingerprint``, a hash of the fact sheet, has not changed, so no model
    call is wasted); at period close the last summary is written and
    ``finalized_at`` freezes the row. ``source`` says whether the model wrote it
    or the plain fact-only fallback was saved.
    Organization-scoped (RLS). See 08_DECISIONS.md 2026-10-21, question 10.
    """

    __tablename__ = "executive_summaries"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_start",
            "period_end",
            name="uq_executive_summaries_one_per_period",
        ),
        CheckConstraint("period_end >= period_start", name="check_executive_summary_period_order"),
        CheckConstraint(
            f"source IN {tuple(s.value for s in SummarySource)}",
            name="check_executive_summary_source",
        ),
        CheckConstraint(
            "length(btrim(summary_text)) > 0",
            name="check_executive_summary_text_not_blank",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization the summary is about",
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False, doc="First day of the period")

    period_end: Mapped[date] = mapped_column(Date, nullable=False, doc="Last day of the period")

    summary_text: Mapped[str] = mapped_column(
        Text, nullable=False, doc="The summary shown on the executive dashboard"
    )

    source: Mapped[SummarySource] = mapped_column(
        String(10),
        nullable=False,
        default=SummarySource.AI.value,
        server_default=SummarySource.AI.value,
        doc="ai (written by the model, numbers checked) or plain (fact-only fallback)",
    )

    facts_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Hash of the fact sheet the summary was written from; an unchanged hash skips the week",
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="When this text was last written (the weekly job replaces it until the period closes)",
    )

    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the period closed and this summary was frozen; empty = still the weekly 'so far' text",
    )
