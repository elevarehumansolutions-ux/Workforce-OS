"""Persistence for blueprint items, plus read-only looks at the structure that already exists."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from app.modules.kpis.models import KPI
from app.modules.okrs.models import OKR
from app.modules.organization.models import Department, Position

from .enums import BlueprintKind, BlueprintStatus
from .models import BlueprintAction, BlueprintItem

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
    BlueprintKind.FOLDED.value,
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

    async def count_live_kpis_of_department(self, department_id: uuid.UUID) -> int:
        """KPIs of a department that are not deleted."""
        stmt = (
            select(func.count())
            .select_from(KPI)
            .where(KPI.department_id == department_id, KPI.deleted_at.is_(None))
        )
        return int(await self._db.scalar(stmt) or 0)

    async def count_live_objectives_of_department(self, department_id: uuid.UUID) -> int:
        """Objectives of a department that are not deleted."""
        stmt = (
            select(func.count())
            .select_from(OKR)
            .where(OKR.department_id == department_id, OKR.deleted_at.is_(None))
        )
        return int(await self._db.scalar(stmt) or 0)

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

    async def list_batch_items(self, batch_id: uuid.UUID) -> list[BlueprintItem]:
        """Every item of one generation run, in the AI's own order (used when reshaping a plan)."""
        stmt = (
            select(BlueprintItem)
            .where(BlueprintItem.batch_id == batch_id)
            .order_by(BlueprintItem.sort_order, BlueprintItem.id)
            .execution_options(populate_existing=True)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def list_department_share_items(self, batch_id: uuid.UUID) -> list[BlueprintItem]:
        """The batch's departments that carry a capital share and have not been skipped.

        These are the ones the capital is split between, in the AI's own order.
        """
        stmt = (
            select(BlueprintItem)
            .where(
                BlueprintItem.batch_id == batch_id,
                BlueprintItem.kind == BlueprintKind.DEPARTMENT.value,
                BlueprintItem.revenue_allocation_pct.is_not(None),
                BlueprintItem.status != BlueprintStatus.REJECTED.value,
            )
            .order_by(BlueprintItem.sort_order, BlueprintItem.id)
            .execution_options(populate_existing=True)
        )
        return list((await self._db.execute(stmt)).scalars().all())

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

    # -- the change history (blueprint_actions) ---------------------------------

    async def list_all_items(self, organization_id: uuid.UUID) -> list[BlueprintItem]:
        """Every plan item of the organization, freshly read (the history snapshots all of them)."""
        stmt = (
            select(BlueprintItem)
            .where(BlueprintItem.organization_id == organization_id)
            .order_by(BlueprintItem.sort_order, BlueprintItem.id)
            .execution_options(populate_existing=True)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def add_action(self, action: BlueprintAction) -> BlueprintAction:
        """Save one recorded change."""
        self._db.add(action)
        await self._db.flush()
        return action

    async def list_actions(self, organization_id: uuid.UUID) -> list[BlueprintAction]:
        """The organization's recorded changes, newest first."""
        stmt = (
            select(BlueprintAction)
            .where(BlueprintAction.organization_id == organization_id)
            .order_by(BlueprintAction.created_at.desc(), BlueprintAction.id)
            .execution_options(populate_existing=True)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_action(self, action_id: uuid.UUID) -> BlueprintAction | None:
        """One recorded change by id, or None (RLS hides other organizations' rows)."""
        stmt = (
            select(BlueprintAction)
            .where(BlueprintAction.id == action_id)
            .execution_options(populate_existing=True)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def delete_actions(self, actions: list[BlueprintAction]) -> None:
        """Forget recorded changes (the undone ones when a new change is made, or the oldest)."""
        for action in actions:
            await self._db.delete(action)
        await self._db.flush()
