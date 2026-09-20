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
    def __init__(self, db: AsyncSession):
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
    def __init__(self, db: AsyncSession):
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


