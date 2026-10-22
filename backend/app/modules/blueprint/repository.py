"""Persistence for blueprint items, plus read-only looks at the structure that already exists."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from app.modules.organization.models import Department, Position

from .enums import BlueprintKind, BlueprintStatus
from .models import BlueprintItem

# Same reason as in the AI suggestions repository: an UPDATE ... RETURNING must
# not guess which in-memory rows it touched, and must refresh the row it returns.
_ATOMIC_UPDATE_OPTIONS = {"synchronize_session": False, "populate_existing": True}

# The order "accept all" applies things in: parents before children.
KIND_ORDER = [
    BlueprintKind.DEPARTMENT.value,
    BlueprintKind.RENAME_DEPARTMENT.value,
    BlueprintKind.POSITION.value,
    BlueprintKind.RENAME_POSITION.value,
    BlueprintKind.OBJECTIVE.value,
    BlueprintKind.KEY_RESULT.value,
    BlueprintKind.KPI.value,
    BlueprintKind.REVIEW_NOTE.value,
]


class BlueprintRepository:
    """Reads and writes ``blueprint_items`` inside an RLS-scoped session."""

    def __init__(self, db: AsyncSession):
        """Initialize with an RLS-scoped async session."""
        self._db = db

    # -- what the company already has (read only) ---------------------------

    async def list_existing_departments(self) -> list[Department]:
        """Every department that is not deleted, oldest first."""
        stmt = (
            select(Department)
            .where(Department.deleted_at.is_(None))
            .order_by(Department.created_at, Department.id)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def list_existing_positions(self) -> list[Position]:
        """Every position that is not deleted, oldest first."""
        stmt = (
            select(Position)
            .where(Position.deleted_at.is_(None))
            .order_by(Position.created_at, Position.id)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    # -- items ---------------------------------------------------------------

    async def has_pending_items(self, organization_id: uuid.UUID) -> bool:
        """True if any item still waits for review (so we do not pile a second batch on top)."""
        stmt = (
            select(BlueprintItem.id)
            .where(
                BlueprintItem.organization_id == organization_id,
                BlueprintItem.status == BlueprintStatus.PENDING.value,
            )
            .limit(1)
        )
        return (await self._db.execute(stmt)).first() is not None

    async def has_any_items(self, organization_id: uuid.UUID) -> bool:
        """True if the organization has ever had a blueprint, reviewed or not."""
        stmt = (
            select(BlueprintItem.id)
            .where(BlueprintItem.organization_id == organization_id)
            .limit(1)
        )
        return (await self._db.execute(stmt)).first() is not None

    async def create_items(self, rows: list[dict]) -> list[BlueprintItem]:
        """Insert a batch of items and return them."""
        items = [BlueprintItem(**row) for row in rows]
        self._db.add_all(items)
        await self._db.flush()
        return items

    async def get_item(self, item_id: uuid.UUID) -> BlueprintItem | None:
        """One item by id, or None (RLS hides other organizations' rows)."""
        # populate_existing: always show what the database holds now, never a stale copy.
        stmt = (
            select(BlueprintItem)
            .where(BlueprintItem.id == item_id)
            .execution_options(populate_existing=True)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get_item_by_ref(self, batch_id: uuid.UUID, ref: str) -> BlueprintItem | None:
        """The item of a batch that carries this ref (how a child finds its parent)."""
        stmt = (
            select(BlueprintItem)
            .where(BlueprintItem.batch_id == batch_id, BlueprintItem.ref == ref)
            .execution_options(populate_existing=True)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def list_items(
        self,
        organization_id: uuid.UUID,
        status: str | None,
        kind: str | None,
        page: int,
        limit: int,
    ) -> PaginationResponse:
        """Page through items in the order the AI gave them (newest batch first)."""
        stmt = select(BlueprintItem).where(BlueprintItem.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(BlueprintItem.status == status)
        if kind is not None:
            stmt = stmt.where(BlueprintItem.kind == kind)
        stmt = stmt.order_by(
            BlueprintItem.created_at.desc(), BlueprintItem.sort_order, BlueprintItem.id
        )
        return await paginate(stmt, page, limit, self._db)

    async def list_pending_items(self, organization_id: uuid.UUID) -> list[BlueprintItem]:
        """All pending items, in the AI's own order (the caller sorts by kind)."""
        stmt = (
            select(BlueprintItem)
            .where(
                BlueprintItem.organization_id == organization_id,
                BlueprintItem.status == BlueprintStatus.PENDING.value,
            )
            .order_by(BlueprintItem.created_at, BlueprintItem.sort_order, BlueprintItem.id)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    # -- review: each one is a single conditional UPDATE ------------------------

    async def review_pending_item(
        self,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        new_status: str,
        reviewed_title: str | None,
    ) -> BlueprintItem | None:
        """Move an item out of 'pending', but only if it is still pending.

        One UPDATE with ``WHERE status = 'pending'``, so two reviewers cannot
        both win. Returns None when nothing changed (unseen, or already reviewed).
        """
        stmt = (
            update(BlueprintItem)
            .where(
                BlueprintItem.id == item_id,
                BlueprintItem.status == BlueprintStatus.PENDING.value,
            )
            .values(
                status=new_status,
                reviewed_title=reviewed_title,
                reviewed_by_user_id=user_id,
                reviewed_at=datetime.now(UTC),
            )
            .returning(BlueprintItem)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def set_created_entity(self, item: BlueprintItem, entity_id: uuid.UUID) -> None:
        """Remember which real row an approved item became."""
        item.created_entity_id = entity_id
        await self._db.flush()
