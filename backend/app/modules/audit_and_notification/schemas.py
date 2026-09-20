"""Pydantic response schemas for the audit log and notifications module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .enums import NotificationCategory


class AuditLogResponse(BaseModel):
    """Serialisable representation of an AuditLog row returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID
    changes: dict | None
    created_at: datetime


class NotificationResponse(BaseModel):
    """Serialisable representation of a Notification row returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    recipient_user_id: UUID
    category: NotificationCategory
    title: str
    body: str | None
    link_type: str | None
    link_id: UUID | None
    read_at: datetime | None
    created_at: datetime


class MarkAllReadResponse(BaseModel):
    """Response for bulk mark-all-notifications-read."""

    marked_read: int
