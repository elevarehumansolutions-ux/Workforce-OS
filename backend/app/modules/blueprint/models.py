"""ORM model for the blueprint: the structure and objectives the AI proposes from Business DNA.

One table, one row per proposed item. Nothing here is a real department,
position or OKR: a real row is created only when HR approves an item
(08_DECISIONS.md 2026-10-22).
"""

from __future__ import annotations

import decimal
import uuid
from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    UUID,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel

from .enums import BlueprintKind, BlueprintStatus


class BlueprintItem(BaseModel):
    """One AI-proposed department, position, objective, key result or clean-up.

    Items that belong together share a ``batch_id`` (one generation run).
    A new item points at its parent in two possible ways, never both:

    * an ``*_id`` column, when the parent already exists as a real row
      (a position proposed inside the company's existing "Sales" department);
    * an ``*_ref`` column, when the parent is another item of the same batch
      that HR has not approved yet (a position inside a proposed department).

    ``created_entity_id`` is filled when an approved item became a real row,
    so the children of that item can find it.
    """

    __tablename__ = "blueprint_items"

    __table_args__ = (
        CheckConstraint(
            f"kind IN {tuple(k.value for k in BlueprintKind)}",
            name="check_blueprint_item_kind",
        ),
        CheckConstraint(
            f"status IN {tuple(s.value for s in BlueprintStatus)}",
            name="check_blueprint_item_status",
        ),
        # A rename must say which existing row it renames.
        CheckConstraint(
            "(kind = 'rename_department' AND department_id IS NOT NULL) OR "
            "(kind = 'rename_position' AND position_id IS NOT NULL) OR "
            "kind NOT IN ('rename_department', 'rename_position')",
            name="check_blueprint_item_rename_has_target",
        ),
        # A KPI proposal must carry its weight.
        CheckConstraint(
            "kind <> 'kpi' OR kpi_weight IS NOT NULL",
            name="check_blueprint_item_kpi_has_weight",
        ),
        # A ref is how items of one batch find each other, so it is unique per batch.
        Index(
            "idx_blueprint_items_batch_ref",
            "organization_id",
            "batch_id",
            "ref",
            unique=True,
            postgresql_where=text("ref IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, doc="One generation run"
    )

    kind: Mapped[str] = mapped_column(String(30), nullable=False)

    ref: Mapped[str | None] = mapped_column(
        String(20), nullable=True, doc="Short key other items of the batch use to point here"
    )

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, doc="The AI's own order, kept for display"
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Department name, position title, objective title, key result text, or the note's heading",
    )

    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    # Parents that already exist as real rows.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True
    )
    reports_to_position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True
    )

    # Parents that are other items of the same batch.
    department_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reports_to_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    objective_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    folded_into_ref: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Only for kind 'folded': the ref of the department or position that covers this one",
    )
    key_result_ref: Mapped[str | None] = mapped_column(
        String(20), nullable=True, doc="The key result a proposed KPI measures, if any"
    )

    # Criticality, proposed by the AI instead of asked of the user. For a department:
    # is_critical and revenue_allocation_pct (its share of the capital investment as an
    # expected-return target; the shares of different departments may add up to more
    # than 100). For a position: is_critical with criticality_type and risk_level.
    is_critical: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    revenue_allocation_pct: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(6, 2), nullable=True
    )
    criticality_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(12), nullable=True)
    profit_margin_pct: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        doc="A department's estimated profit margin (0-100), proposed with its capital share",
    )

    # Only for kind 'kpi' (title is the KPI's name, department_* its department).
    kpi_weight: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(5, 2), nullable=True, doc="Share of its department's KPIs, in percent"
    )
    kpi_target_value: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(14, 2), nullable=True
    )
    kpi_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    kpi_is_inverse: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, doc="True when a lower figure is better (for example days to deliver)"
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=BlueprintStatus.PENDING.value,
        server_default=BlueprintStatus.PENDING.value,
    )

    reviewed_title: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="The final wording HR decided; null while pending and on rejection"
    )

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="The real department, position, OKR or key result this item became",
    )

    merge_record: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc=(
            "Only on a left-out note made by a merge: what the merge changed on the plan's items "
            "(their old values), so 'Undo merge' can put everything back exactly"
        ),
    )

    @property
    def can_undo_merge(self) -> bool:
        """True when this left-out note remembers the merge that made it."""
        return self.merge_record is not None


class BlueprintAction(BaseModel):
    """One change the owner made to the plan while reviewing it, kept so it can be undone and redone.

    Only the onboarding review writes these. ``changes`` holds, for every plan item the change
    touched, each column's old and new value: undo puts the old ones back, and compares the
    current ones with the new ones first, so a change is never undone on top of a later one.
    """

    __tablename__ = "blueprint_actions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, doc="approve, edit, reject, merge, add_separately or accept_all"
    )
    label: Mapped[str] = mapped_column(Text, nullable=False, doc="What the owner reads in the history")
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, doc="What redo needs to run the same change again (item ids, wording)"
    )
    changes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, doc="{item id: {column: [old value, new value]}} for every item touched"
    )
    real_names: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="{rename item id: the real department or role's name before}, so a rename can be put back",
    )
    undone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Set while the change is undone (it can be redone)"
    )
