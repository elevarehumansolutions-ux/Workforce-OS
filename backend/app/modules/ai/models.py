"""ORM models for Cluster 4 (Strategy): AI Suggestions and usage metering.

Contains:
- :class:`AISuggestion`: an AI-proposed change to org structure, pending
  human review (approve/edit/reject) before it ever touches a real row.
- :class:`AIUsageLog`: one row per LLM API call, for cost/usage tracking.

M7 shipped three suggestion types (``critical_position``,
``revenue_allocation``, ``missing_department``); ``kpi_weight`` was added
in M8 once ``kpis`` existed (08_DECISIONS.md 2026-09-30).
"""

from __future__ import annotations

import decimal
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DECIMAL,
    UUID,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    column,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel
from app.core.text import normalized_name_expr

from .enums import AIUsagePurpose, SuggestionStatus, SuggestionType

if TYPE_CHECKING:
    from app.modules.organization.models import Department, Position
    from app.modules.tenancy_identity.models import Organization, User
    from app.modules.kpis.models import KPI


class AISuggestion(BaseModel):
    """An AI-proposed change, held for human review before taking effect.

    Organization-scoped (RLS restricts rows to the caller's current org).
    Not soft-deletable — a suggestion's lifecycle is its ``status``
    (pending/approved/edited/rejected), never a delete. One table serves
    all suggestion types rather than one table per type, trading unused
    nullable columns per row for a single shared review lifecycle.

    Idempotency has two independent layers, deliberately not one:

    1. **Pending-duplicate prevention** (2026-09-07): a partial unique index
       on (``organization_id``, ``suggestion_type``, ``position_id``,
       ``department_id``, ``suggested_department_name_normalized``)
       ``WHERE status = 'pending'``, paired with an ``INSERT ... ON CONFLICT
       DO NOTHING`` in the generation code. A hard database guarantee,
       because a check-then-insert here has a real race under concurrent
       Celery execution. It keys on the *normalized* department name (a
       generated column, ``NULLS NOT DISTINCT``) rather than the raw text,
       since the name is free text from an LLM — see 08_DECISIONS.md
       2026-09-23. The raw ``suggested_department_name`` is kept untouched
       for display and as the unaltered AI signal.
    2. **Rejected-suggestion quarterly suppression** (2026-09-22): once a
       suggestion for a given target is rejected, generation code checks
       for a matching rejected row with ``reviewed_at`` inside the org's
       *current* fiscal quarter (derived from
       ``organizations.fiscal_year_start_month``) before creating a new
       pending one for that same target, and skips it if found. This can't
       be a database constraint — an index predicate referencing ``now()``
       isn't immutable — so it's an application-level check. It doesn't
       need to be race-proof the way (1) does: if two concurrent runs both
       pass this check, the partial unique index in (1) still absorbs the
       resulting duplicate insert. The two layers are complementary, not
       redundant.

    ``reviewed_at``/``reviewed_by_user_id`` are populated on every review
    decision, including rejection — suppression (2) depends on this. Only
    the mirrored *value* columns (``reviewed_criticality_type`` etc.) stay
    null on rejection, since there's no "correct" value to record when the
    suggestion was simply turned down.
    """

    __tablename__ = "ai_suggestions"

    __table_args__ = (
        CheckConstraint(
            f"suggestion_type IN {tuple(t.value for t in SuggestionType)}",
            name="check_ai_suggestion_type",
        ),
        CheckConstraint(
            f"status IN {tuple(s.value for s in SuggestionStatus)}",
            name="check_ai_suggestion_status",
        ),
        CheckConstraint(
            "(suggestion_type = 'critical_position' AND position_id IS NOT NULL "
            "AND suggested_criticality_type IS NOT NULL AND suggested_risk_level IS NOT NULL) OR "
            "(suggestion_type = 'revenue_allocation' AND department_id IS NOT NULL "
            "AND suggested_revenue_allocation_percentage IS NOT NULL) OR "
            "(suggestion_type = 'missing_department' AND suggested_department_name IS NOT NULL) OR "
            "(suggestion_type = 'kpi_weight' AND kpi_id IS NOT NULL "
            "AND suggested_weight IS NOT NULL)",
            name="check_ai_suggestion_target_matches_type",
        ),
        Index(
            "idx_ai_suggestions_unique_pending",
            "organization_id",
            "suggestion_type",
            "position_id",
            "department_id",
            "suggested_department_name_normalized",
            "kpi_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            postgresql_nulls_not_distinct=True,
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this suggestion belongs to",
    )

    suggestion_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="Kind of suggestion — determines which target column is set",
    )

    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("positions.id"),
        nullable=True,
        index=True,
        doc="Target position — set for 'critical_position'",
    )

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=True,
        index=True,
        doc="Target department — set for 'revenue_allocation'",
    )

    suggested_department_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Proposed name for a new department — set for 'missing_department', no row exists yet",
    )

    suggested_department_name_normalized: Mapped[str | None] = mapped_column(
        Text,
        Computed(
            normalized_name_expr(column("suggested_department_name")),
            persisted=True,
        ),
        nullable=True,
        doc=(
            "Database-derived comparison key for suggested_department_name "
            "(never written by the application) — what the pending-duplicate "
            "index and the rejection lookup actually match on"
        ),
    )

    suggested_criticality_type: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="AI-proposed criticality type"
    )

    suggested_risk_level: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="AI-proposed risk level"
    )

    suggested_revenue_allocation_percentage: Mapped[decimal.Decimal | None] = (
        mapped_column(
            DECIMAL(6, 2),
            nullable=True,
            doc="AI-proposed revenue allocation percentage",
        )
    )

    kpi_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kpis.id"),
        nullable=True,
        index=True,
        doc="Target KPI — set for 'kpi_weight'",
    )

    suggested_weight: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2), nullable=True, doc="AI-proposed KPI weight"
    )

    rationale: Mapped[str] = mapped_column(
        Text, nullable=False, doc="AI-generated explanation for the suggestion"
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SuggestionStatus.PENDING.value,
        server_default=SuggestionStatus.PENDING.value,
        doc="Review lifecycle state",
    )

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        doc="User who made the review decision — set on approve, edit, or reject",
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc=(
            "When the review decision was made — set on approve, edit, or "
            "reject. Load-bearing for the rejected-suggestion quarterly "
            "suppression check, not just an audit timestamp."
        ),
    )

    reviewed_criticality_type: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Final human-decided criticality type — mirrors suggested_criticality_type; null on rejection",
    )

    reviewed_risk_level: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Final human-decided risk level — mirrors suggested_risk_level; null on rejection",
    )

    reviewed_revenue_allocation_percentage: Mapped[decimal.Decimal | None] = (
        mapped_column(
            DECIMAL(6, 2),
            nullable=True,
            doc=(
                "Final human-decided revenue allocation percentage — "
                "mirrors suggested_revenue_allocation_percentage; null on rejection"
            ),
        )
    )

    reviewed_department_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Final human-decided department name — mirrors suggested_department_name; null on rejection",
    )

    reviewed_weight: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        doc="Final human-decided KPI weight — mirrors suggested_weight; null on rejection",
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="ai_suggestions"
    )
    position: Mapped["Position | None"] = relationship(
        "Position", back_populates="ai_suggestions"
    )
    department: Mapped["Department | None"] = relationship(
        "Department", back_populates="ai_suggestions"
    )
    kpi: Mapped["KPI | None"] = relationship(
        "KPI", back_populates="ai_suggestions"
    )
    reviewed_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[reviewed_by_user_id]
    )


class AIUsageLog(BaseModel):
    """One row per LLM API call, for per-organization cost/usage tracking.

    Organization-scoped (RLS restricts rows to the caller's current org).
    Attaches to the call itself, not to individual suggestions — one call
    can produce several suggestions at once, so cost can't be meaningfully
    split across its results. Written through the shared internal
    LLM-calling utility, not duplicated per caller.
    """

    __tablename__ = "ai_usage_log"

    __table_args__ = (
        CheckConstraint(
            f"purpose IN {tuple(p.value for p in AIUsagePurpose)}",
            name="check_ai_usage_log_purpose",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this LLM call was made on behalf of",
    )

    purpose: Mapped[str] = mapped_column(
        String(40), nullable=False, doc="What this LLM call was for"
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Model id that served this call (e.g. claude-sonnet-5), for per-model cost tracking",
    )

    prompt_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="Prompt tokens consumed by this call"
    )

    completion_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="Completion tokens generated by this call"
    )

    cache_write_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        doc="Input tokens written to the prompt cache (5-minute and 1-hour combined)",
    )

    cache_read_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        doc="Input tokens served from the prompt cache",
    )

    estimated_cost_usd: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(10, 4), nullable=True, doc="Estimated cost of this call in USD"
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="ai_usage_logs"
    )
