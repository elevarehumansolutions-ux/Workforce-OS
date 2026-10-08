"""FastAPI routes for reading the audit trail and managing notifications."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_membership, require_org_role
from app.core.schemas import CursorPaginationMeta, CursorPaginationResponse
from app.modules.tenancy_identity.models import Membership
from .enums import NotificationCategory
from .schemas import AuditLogResponse, MarkAllReadResponse, NotificationResponse
from .service import AuditService, NotificationService

router = APIRouter()

# Every mutating action across every module writes to audit_log, so unlike
# notifications (self-scoped by recipient_user_id, safe for any role) this
# is org-wide sensitive change history — restricted the same way
# GET /billing/history and GET /ai-usage are.
_AUDIT_LOG_ROLES = ("hr_administrator", "business_executive")


@router.get("/audit-log", status_code=200)
async def list_audit_log(
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_AUDIT_LOG_ROLES)),
) -> CursorPaginationResponse:
    """List the org-wide audit trail, cursor-paginated and filterable.

    No viewer screen for MVP, reachable via API for support/debugging use
    per 07_SECURITY.md. Restricted to hr_administrator/business_executive
    roles via ``require_org_role``.
    """
    service = AuditService(db)
    result = await service.list_audit_log(
        organization_id=caller.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
        limit=limit,
    )
    return CursorPaginationResponse(
        message="OK",
        data=[AuditLogResponse.model_validate(item) for item in result["items"]],
        pagination=CursorPaginationMeta(
            next_cursor=result["next_cursor"],
            count=result["count"],
            total=result["total"],
        ),
    )


@router.get("/notifications", status_code=200)
async def list_notifications(
    category: NotificationCategory | None = Query(default=None),
    unread: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> list[NotificationResponse]:
    """List the caller's own notification stream, optionally filtered.

    Self-scoped by recipient_user_id, no role restriction — every role
    gets their own stream, per 04_DATABASE.md Cluster 8's design note.
    """
    service = NotificationService(db)
    notifications = await service.list_notifications(
        organization_id=caller.organization_id,
        recipient_user_id=caller.user_id,
        category=category,
        unread=unread,
    )
    return [NotificationResponse.model_validate(n) for n in notifications]


@router.post("/notifications/{notification_id}/read", status_code=200)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> NotificationResponse:
    """Mark one of the caller's own notifications as read and commit.

    Raises:
        NotificationNotFoundException: If no notification with that id
            exists for the caller (also covers another user's notification
            id, since the lookup is scoped to the caller).

    """
    service = NotificationService(db)
    notification = await service.mark_read(
        notification_id=notification_id,
        recipient_user_id=caller.user_id,
    )
    await db.commit()
    return NotificationResponse.model_validate(notification)


@router.post("/notifications/read-all", status_code=200)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> MarkAllReadResponse:
    """Mark all of the caller's unread notifications as read and commit."""
    service = NotificationService(db)
    count = await service.mark_all_read(
        organization_id=caller.organization_id,
        recipient_user_id=caller.user_id,
    )
    await db.commit()
    return MarkAllReadResponse(marked_read=count)
