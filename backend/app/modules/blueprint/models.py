"""ORM model for the blueprint: the structure and objectives the AI proposes from Business DNA.

One table, one row per proposed item. Nothing here is a real department,
position or OKR: a real row is created only when HR approves an item
(08_DECISIONS.md 2026-10-22).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
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
