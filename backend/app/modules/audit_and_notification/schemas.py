"""Pydantic response schemas for the audit log and notifications module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import NotificationCategory


class AuditLogResponse(BaseModel):
    """Serialisable representation of an AuditLog row returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    actor_user_id: UUID | None
    # The actor's full name, so the screen does not have to look it up (a business executive
    # cannot read the team list). None for system actions or a user that no longer exists.
    actor_name: str | None = None
    # What the row was about, in words: "Chidi Okafor (chidi@x.com)", "Sales". None when unknown.
    subject: str | None = None
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


class UnreadCountResponse(BaseModel):
    """How many notifications the caller has not read (the number on the bell)."""

    unread: int


class ReadByLinkRequest(BaseModel):
    """Which thing the person has just opened: its kind (for example ``task``) and id."""

    link_type: str = Field(min_length=1, max_length=50)
    link_id: UUID


class MarkAllReadResponse(BaseModel):
    """Response for bulk mark-all-notifications-read."""

    marked_read: int
