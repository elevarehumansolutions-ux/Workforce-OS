"""Business logic for recording audit log entries and dispatching notifications."""

import logging
import uuid

from datetime import datetime

from .enums import NotificationCategory

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import AuditRepository, NotificationRepository
from .models import AuditLog, Notification

logger = logging.getLogger(__name__)


class AuditService:
    """Writes and reads audit log entries on behalf of other modules."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with an async database session."""
        self._db = db
        self._repo = AuditRepository(db)

    async def log_action(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        changes: dict | None = None,
    ) -> AuditLog:
        """Record one audit_log row.

        Never commits — the caller's own transaction decides when this
        becomes durable, so a failed caller rolls the audit entry back
        along with everything else.

        Args:
            organization_id: Organization the logged action belongs to.
            actor_user_id: User who performed the action, or ``None`` if
                the action wasn't performed by an authenticated user.
            action: Short description/name of the action performed.
            entity_type: Type of the entity the action was performed on.
            entity_id: Id of the entity the action was performed on.
            changes: Optional JSON-serializable diff of what changed.

        Returns:
            The newly created ``AuditLog`` instance.

        """
        log = await self._repo.create_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
        )
        # DEBUG, not INFO: every mutating action in the app calls this, so
        # at INFO it would double every other business-event log line.
        # audit_log itself (GET /audit-log) is the actual queryable trail;
        # this is only for local debugging of the logging path itself.
        logger.debug(
            "Audit log recorded",
            extra={
                "organization_id": str(organization_id),
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
            },
        )
        return log

    async def list_audit_log(
        self,
        *,
        organization_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict:
        """List audit log rows for an organization, cursor-paginated and filtered.

        Args:
            organization_id: Organization whose audit trail is being read.
            entity_type: If given, only rows for this entity type.
            entity_id: If given, only rows for this entity id.
            actor_user_id: If given, only rows performed by this user.
            date_from: If given, only rows created on/after this time.
            date_to: If given, only rows created on/before this time.
            cursor: Opaque pagination cursor from a previous page, if any.
            limit: Maximum number of rows to return in this page.

        Returns:
            The cursor-paginated result dict produced by the repository.

        """
        return await self._repo.list_audit_log(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )


class NotificationService:
    """Creates and reads in-app notifications on behalf of other modules."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with an async database session."""
        self._db = db
        self._repo = NotificationRepository(db)

    async def notify(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_ids: list[uuid.UUID],
        category: NotificationCategory,
        title: str,
        body: str | None = None,
        link_type: str | None = None,
        link_id: uuid.UUID | None = None,
    ) -> None:
        """Create one notification row per recipient in a single bulk write.

        Always takes a list, even for one recipient — one contract, no
        per-call-site decision about which function to use. Never commits,
        same reasoning as ``AuditService.log_action``.

        Args:
            organization_id: Organization the notifications belong to.
            recipient_user_ids: Users to notify — one row is created per id.
            category: Notification category (see ``NotificationCategory``).
            title: Notification title shown to the recipient.
            body: Optional longer notification body text.
            link_type: Optional type of entity this notification links to.
            link_id: Optional id of the entity this notification links to.

        """
        await self._repo.create_notifications(
            organization_id=organization_id,
            recipient_user_ids=recipient_user_ids,
            category=category,
            title=title,
            body=body,
            link_type=link_type,
            link_id=link_id,
        )
        # INFO: a real, boundable business event (one notify() call, however
        # many recipients) — this is what you'd grep for to answer "did the
        # AI suggestion / overdue-task notification actually fire" without
        # needing DB access.
        logger.info(
            "Notification(s) created",
            extra={
                "organization_id": str(organization_id),
                "recipient_count": len(recipient_user_ids),
                "category": category,
            },
        )

    async def list_notifications(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        category: NotificationCategory | None = None,
        unread: bool = False,
    ) -> list[Notification]:
        """List a recipient's notifications for an org, newest first.

        Args:
            organization_id: Organization the notifications belong to.
            recipient_user_id: User whose notification stream is read.
            category: If given, only notifications of this category.
            unread: If True, only notifications with no ``read_at`` set.

        Returns:
            The matching notifications ordered by creation time, newest first.

        """
        return await self._repo.list_notifications(
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
            category=category,
            unread=unread,
        )

    async def mark_read(
        self,
        *,
        notification_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
    ) -> Notification:
        """Mark a single notification read, scoped to its recipient.

        Args:
            notification_id: Id of the notification to mark read.
            recipient_user_id: Id of the user the notification must belong
                to, to prevent one user from marking another's notification
                read.

        Returns:
            The updated ``Notification`` instance.

        Raises:
            NotificationNotFoundException: If no notification with that id
                exists for that recipient.

        """
        return await self._repo.mark_read(
            notification_id=notification_id,
            recipient_user_id=recipient_user_id,
        )

    async def mark_all_read(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
    ) -> int:
        """Mark every unread notification for a recipient in an org as read.

        Args:
            organization_id: Organization the notifications belong to.
            recipient_user_id: User whose unread notifications are marked read.

        Returns:
            The number of rows updated.

        """
        return await self._repo.mark_all_read(
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
        )
        
