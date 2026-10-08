"""ORM models for Cluster 5 (Performance): KPIs.

Contains :class:`KPI` — a department- or location-scoped key performance
indicator — and :class:`KPIScore` — one recorded actual value for a KPI in
a given scoring period.
"""

from __future__ import annotations

import decimal
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DECIMAL, UUID, CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel
from .enums import KPITrackingMode

if TYPE_CHECKING:
    from app.modules.tenancy_identity.models import Organization
    from app.modules.organization.models import Department, Location
    from app.modules.okrs.models import KeyResult
    from app.modules.ai.models import AISuggestion


class KPI(BaseModel):
    """A department- or location-scoped key performance indicator.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. ``location_id`` null means department-wide; set scopes
    it to one location (the branch/store model, same as OKRs).
    ``key_result_id`` is nullable — not every KPI traces back to a specific
    Key Result, some are purely operational and support strategy generally
    without tying to one measurable target.

    ``weight`` is checked at the row level (0-100) but summing to 100 across
    a department/location group is an application-level rule, not a
    database constraint — Postgres has no clean row-level way to check a
    *group* of rows sums to 100 (08_DECISIONS.md 2026-09-29).
    """

    __tablename__ = "kpis"

    __table_args__ = (
        CheckConstraint(
            "weight >= 0 AND weight <= 100", name="check_kpi_weight_range"
        ),
        CheckConstraint(
            f"tracking_mode IN {tuple(m.value for m in KPITrackingMode)}",
            name="check_kpi_tracking_mode",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this KPI belongs to",
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
        doc="Department this KPI belongs to",
    )

    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
        doc="Location this KPI is scoped to; null means department-wide",
    )

    key_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("key_results.id"),
        nullable=True,
        index=True,
        doc="Key Result this KPI traces to; null if purely operational",
    )

    name: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Name of the KPI"
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Description of the KPI"
    )

    weight: Mapped[decimal.Decimal] = mapped_column(
        DECIMAL(5, 2),
        nullable=False,
        doc="Weight of this KPI within its department/location group (0-100)",
    )

    is_inverse: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc=(
            "Whether a lower actual_value is better for this KPI (e.g. "
            "'customer complaints') — flips how score_percentage is "
            "calculated from actual vs target"
        ),
    )

    target_value: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(14, 2),
        nullable=True,
        doc="Target value this KPI is measured against",
    )

    unit: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Unit the target/actual values are measured in"
    )

    tracking_mode: Mapped[KPITrackingMode] = mapped_column(
        String(20),
        nullable=False,
        default=KPITrackingMode.MANUAL.value,
        server_default=KPITrackingMode.MANUAL.value,
        doc=(
            "How this KPI's mid-quarter progress is known: 'manual' "
            "(typed in via POST /kpis/{id}/scores) or 'task_count' (live "
            "count of completed tasks linked to this KPI)"
        ),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the KPI is deleted.",
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="kpis"
    )
    department: Mapped["Department"] = relationship(
        "Department", back_populates="kpis"
    )
    location: Mapped["Location | None"] = relationship(
        "Location", back_populates="kpis"
    )
    key_result: Mapped["KeyResult | None"] = relationship(
        "KeyResult", back_populates="kpis"
    )
    scores: Mapped[list["KPIScore"]] = relationship(
        "KPIScore", back_populates="kpi"
    )
    ai_suggestions: Mapped[list["AISuggestion"]] = relationship(
        "AISuggestion", back_populates="kpi"
    )


class KPIScore(BaseModel):
    """One recorded actual value for a :class:`KPI` in a given scoring period.

    Organization-scoped (RLS restricts rows to the caller's current org).
    Deliberately **not** soft-deletable, a deviation from this codebase's
    usual convention — a closed period's score is permanent history, a
    correction is a new period's row, not an edit to the old one (same
    reasoning as ``workflow_instances``, 04_DATABASE.md Cluster 5).
    """

    __tablename__ = "kpi_scores"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this score belongs to",
    )

    kpi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kpis.id"),
        nullable=False,
        index=True,
        doc="KPI this score is recorded for",
    )

    period_start: Mapped[date] = mapped_column(
        Date, nullable=False, doc="Start date of the scoring period"
    )

    period_end: Mapped[date] = mapped_column(
        Date, nullable=False, doc="End date of the scoring period"
    )

    actual_value: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(14, 2), nullable=True, doc="Actual recorded value for the period"
    )

    score_percentage: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        doc=(
            "Actual-vs-target performance as a percentage, computed and "
            "stored by the application (handles inverse KPIs), not derived "
            "on read"
        ),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="kpi_scores"
    )
    kpi: Mapped["KPI"] = relationship("KPI", back_populates="scores")
