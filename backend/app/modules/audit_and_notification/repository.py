"""Data-access layer for audit log entries and in-app notifications."""

import logging
import uuid
from datetime import datetime, UTC

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog, Notification
from .enums import NotificationCategory
from app.core.pagination import paginate_cursor
from app.core.exceptions import NotificationNotFoundException

logger = logging.getLogger(__name__)


class AuditRepository:
    """Persistence layer for :class:`~app.modules.audit_and_notification.models.AuditLog` rows."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an async database session."""
        self._db = db

    async def create_audit_log(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        changes: dict | None = None,
    ) -> AuditLog:
        """Build, add, and flush a new audit log row.

        Does not commit — the caller's transaction controls durability.

        Args:
            organization_id: Organization the logged action belongs to.
            actor_user_id: User who performed the action, or ``None`` if
                the action wasn't performed by an authenticated user.
            action: Short description/name of the action performed.
            entity_type: Type of the entity the action was performed on.
            entity_id: Id of the entity the action was performed on.
            changes: Optional JSON-serializable diff of what changed.

        Returns:
            The newly created and refreshed ``AuditLog`` instance.

        """
        audit_log = AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
        )
        self._db.add(audit_log)
        await self._db.flush()
        await self._db.refresh(audit_log)
        return audit_log
    
    async def list_audit_log(
        self,
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
            The cursor-paginated result dict produced by ``paginate_cursor``.

        """
        query = select(AuditLog).where(AuditLog.organization_id == organization_id)
        if entity_type is not None:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(AuditLog.entity_id == entity_id)
        if actor_user_id is not None:
            query = query.where(AuditLog.actor_user_id == actor_user_id)
        if date_from is not None:
            query = query.where(AuditLog.created_at >= date_from)
        if date_to is not None:
            query = query.where(AuditLog.created_at <= date_to)

        return await paginate_cursor(query, self._db, AuditLog, cursor=cursor, limit=limit)



class NotificationRepository:
    """Persistence layer for :class:`~app.modules.audit_and_notification.models.Notification` rows."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an async database session."""
        self._db = db

    async def create_notifications(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_ids: list[uuid.UUID],
        category: NotificationCategory,
        title: str,
        body: str | None = None,
        link_type: str | None = None,
        link_id: uuid.UUID | None = None,
    ) -> list[Notification]:
        """Create and flush one notification row per recipient in bulk.

        Args:
            organization_id: Organization the notifications belong to.
            recipient_user_ids: Users to notify — one row is created per id.
            category: Notification category (see ``NotificationCategory``).
            title: Notification title shown to the recipient.
            body: Optional longer notification body text.
            link_type: Optional type of entity this notification links to.
            link_id: Optional id of the entity this notification links to.

        Returns:
            The newly created ``Notification`` rows, one per recipient.

        """
        rows = [
            Notification(
                organization_id=organization_id,
                recipient_user_id=recipient_id,
                category=category,
                title=title,
                body=body,
                link_type=link_type,
                link_id=link_id,
            )
            for recipient_id in recipient_user_ids
        ]
        self._db.add_all(rows)
        await self._db.flush()
        return rows

    async def list_notifications(
        self,
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
            The matching ``Notification`` rows ordered by ``created_at`` desc.

        """
        query = select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == recipient_user_id,
        )
        if category is not None:
            query = query.where(Notification.category == category)
        if unread:
            query = query.where(Notification.read_at.is_(None))
        query = query.order_by(Notification.created_at.desc())

        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
    ) -> Notification:
        """Mark a single notification read, scoped to its recipient.

        Logs a warning and raises if no matching row is found, since that
        indicates either stale client state or a user probing another
        user's notification ids.

        Args:
            notification_id: Id of the notification to mark read.
            recipient_user_id: Id of the user the notification must belong
                to — the lookup is scoped by this to prevent one user from
                marking another's notification read.

        Returns:
            The updated ``Notification`` instance.

        Raises:
            NotificationNotFoundException: If no notification with that id
                exists for that recipient.

        """
        query = select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == recipient_user_id,
        )
        result = await self._db.execute(query)
        notification = result.scalar_one_or_none()
        if notification is None:
            # WARNING, not silent: either stale client state (a notification
            # that got deleted/reassigned) or someone probing another
            # user's notification ids — worth being able to grep for.
            logger.warning(
                "Notification mark-read failed: not found for recipient",
                extra={
                    "notification_id": str(notification_id),
                    "recipient_user_id": str(recipient_user_id),
                },
            )
            raise NotificationNotFoundException()

        notification.read_at = datetime.now(UTC)
        await self._db.flush()
        return notification

    async def mark_all_read(
        self,
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
        stmt = (
            update(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.recipient_user_id == recipient_user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
        result = await self._db.execute(stmt)
        return result.rowcount


