from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import (
    CheckConstraint,
    Index,
    UUID,
    ForeignKey,
    Text,
    DateTime
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel
from .enums import NotificationCategory

if TYPE_CHECKING:
    from app.modules.tenancy_identity.models import User, Organization

class AuditLog(BaseModel):
    __tablename__ = "audit_log"

    __table_args__ = (
        Index("idx_audit_log_org_entity", "organization_id", "entity_type", "entity_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this log belongs to",
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User performing the action",
    )
    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Action being performed",
    )
    entity_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Type of entity being acted upon",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="ID of the entity being acted upon",
    )
    changes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="audit_logs"
    )
    actor_user: Mapped["User"] = relationship(
        "User",
        back_populates="audit_logs"
    )


class Notification(BaseModel):
    __tablename__ = "notifications"

    __table_args__ = (
        Index("idx_notification_recipient", "organization_id", "recipient_user_id", "read_at", "created_at"),
        CheckConstraint(
            f"category IN {tuple(c.value for c in NotificationCategory)}",
            name="check_notification_category",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Organization this notification belongs to",
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who will receive this notification",
    )
    category: Mapped[NotificationCategory] = mapped_column(
        Text,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    link_type: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="notifications"
    )
    recipient_user: Mapped["User"] = relationship(
        "User",
        back_populates="notifications"
    )
