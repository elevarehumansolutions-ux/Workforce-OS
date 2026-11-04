"""Business logic for reviewing blueprint items.

Approving an item creates the real department, position, OKR or key result
through that module's own service (so every rule it already enforces still
applies). Never commits: the router owns the transaction, so a failed apply
rolls the review back too.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BlueprintItemAlreadyReviewedException,
    BlueprintItemNotFoundException,
    BlueprintParentRejectedException,
    PlatformError,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.service import AuditService
from app.modules.kpis.schemas import KPICreate
from app.modules.kpis.service import KPIService
from app.modules.okrs.service import KeyResultService, OKRService
from app.modules.organization.service import DepartmentService, PositionService

from .enums import BlueprintKind, BlueprintStatus
from .models import BlueprintItem
from .repository import KIND_ORDER, BlueprintRepository
from .schemas import AcceptAllResponse, AcceptAllSkipped


class BlueprintService:
    """Approve, edit and reject blueprint items, or accept them all at once."""

    def __init__(self, db: AsyncSession):
        """Initialize with an RLS-scoped session and the services that create real rows."""
        self._db = db
        self._repo = BlueprintRepository(db)
        self._audit = AuditService(db)
        self._departments = DepartmentService(db)
        self._positions = PositionService(db)
        self._okrs = OKRService(db)
        self._key_results = KeyResultService(db)
        self._kpis = KPIService(db)

    async def list_items(
        self,
        organization_id: uuid.UUID,
        status: str | None,
        kind: str | None,
        page: int,
        limit: int,
    ) -> PaginationResponse:
        """A page of the organization's blueprint items."""
        return await self._repo.list_items(organization_id, status, kind, page, limit)

    # -- applying an item -------------------------------------------------------

    async def _entity_id_of_parent(
        self, batch_id: uuid.UUID, ref: str, actor_user_id: uuid.UUID
    ) -> uuid.UUID:
        """The real row behind a parent item of the same batch, approving it first if needed.

        Raises:
            BlueprintItemNotFoundException: No item of the batch has that ref.
            BlueprintParentRejectedException: HR rejected the parent.
        """
        parent = await self._repo.get_item_by_ref(batch_id, ref)
        if parent is None:
            raise BlueprintItemNotFoundException()
        if parent.status == BlueprintStatus.PENDING.value:
            await self._claim_and_apply(
                parent.id, actor_user_id, BlueprintStatus.APPROVED.value, parent.title
            )
        elif parent.status == BlueprintStatus.REJECTED.value:
            raise BlueprintParentRejectedException(
                message=f"'{parent.title}' was rejected, so this item cannot be applied"
            )
        return parent.created_entity_id

    async def _department_for(
        self, item: BlueprintItem, actor_user_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The real department an item sits in: an existing one, or the one its parent became."""
        if item.department_id is not None:
            return item.department_id
        if item.department_ref is not None:
            return await self._entity_id_of_parent(item.batch_id, item.department_ref, actor_user_id)
        return None

    async def _boss_position_for(
        self, item: BlueprintItem, actor_user_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The real position a position reports to, or None when the boss was rejected."""
        if item.reports_to_position_id is not None:
            return item.reports_to_position_id
        if item.reports_to_ref is None:
            return None
        try:
            return await self._entity_id_of_parent(item.batch_id, item.reports_to_ref, actor_user_id)
        except BlueprintParentRejectedException:
            # Losing a boss only leaves a gap in the chart; HR can fix it later.
            return None

    async def _key_result_for(
        self, item: BlueprintItem, actor_user_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The real key result a KPI measures, or None when it has none or it was rejected."""
        if item.key_result_ref is None:
            return None
        try:
            return await self._entity_id_of_parent(item.batch_id, item.key_result_ref, actor_user_id)
        except BlueprintParentRejectedException:
            # The link is optional: a KPI is still useful without its key result.
            return None

    async def _apply(self, item: BlueprintItem, actor_user_id: uuid.UUID) -> None:
        """Create or change the real row this item stands for."""
        org_id = item.organization_id
        text = item.reviewed_title

        if item.kind == BlueprintKind.DEPARTMENT.value:
            created = await self._departments.create_department(org_id, actor_user_id, {"name": text})
        elif item.kind == BlueprintKind.POSITION.value:
            department_id = await self._department_for(item, actor_user_id)
            boss_id = await self._boss_position_for(item, actor_user_id)
            created = await self._positions.create_position(
                org_id,
                actor_user_id,
                {"title": text, "department_id": department_id, "reports_to_position_id": boss_id},
            )
        elif item.kind == BlueprintKind.OBJECTIVE.value:
            department_id = await self._department_for(item, actor_user_id)
            created = await self._okrs.create_okr(
                org_id, actor_user_id, {"title": text, "department_id": department_id}
            )
        elif item.kind == BlueprintKind.KEY_RESULT.value:
            okr_id = await self._entity_id_of_parent(item.batch_id, item.objective_ref, actor_user_id)
            created = await self._key_results.create_key_result(
                okr_id, actor_user_id, {"description": text}
            )
        elif item.kind == BlueprintKind.KPI.value:
            department_id = await self._department_for(item, actor_user_id)
            key_result_id = await self._key_result_for(item, actor_user_id)
            # create_kpi refuses (409) a weight that would push the department over 100%.
            created = await self._kpis.create_kpi(
                org_id,
                actor_user_id,
                KPICreate(
                    department_id=department_id,
                    key_result_id=key_result_id,
                    name=text,
                    description=item.rationale,
                    weight=item.kpi_weight,
                    is_inverse=bool(item.kpi_is_inverse),
                    target_value=item.kpi_target_value,
                    unit=item.kpi_unit,
                ),
            )
        elif item.kind == BlueprintKind.RENAME_DEPARTMENT.value:
            created = await self._departments.update_department(
                item.department_id, actor_user_id, {"name": text}
            )
        elif item.kind == BlueprintKind.RENAME_POSITION.value:
            created = await self._positions.update_position(
                item.position_id, actor_user_id, {"title": text}
            )
        else:
            # A review note: approving it just means "seen", nothing to create.
            return
        await self._repo.set_created_entity(item, created.id)

    async def _claim_and_apply(
        self,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        new_status: str,
        reviewed_title: str,
    ) -> BlueprintItem:
        """Claim a pending item atomically, apply it, and write the audit entry."""
        claimed = await self._repo.review_pending_item(
            item_id, actor_user_id, new_status, reviewed_title
        )
        if claimed is None:
            raise BlueprintItemAlreadyReviewedException()
        await self._apply(claimed, actor_user_id)
        await self._audit.log_action(
            organization_id=claimed.organization_id,
            actor_user_id=actor_user_id,
            action="approve" if new_status == BlueprintStatus.APPROVED.value else "edit",
            entity_type="blueprint_item",
            entity_id=claimed.id,
            changes={
                "old": {"status": BlueprintStatus.PENDING.value},
                "new": {"status": new_status, "title": reviewed_title},
            },
        )
        return claimed

    async def _get_pending_item(self, item_id: uuid.UUID) -> BlueprintItem:
        """The item, or 404 if unseen, or 409 if it was already reviewed."""
        item = await self._repo.get_item(item_id)
        if item is None:
            raise BlueprintItemNotFoundException()
        if item.status != BlueprintStatus.PENDING.value:
            raise BlueprintItemAlreadyReviewedException()
        return item

    # -- the endpoints' actions -----------------------------------------------------

    async def approve_item(self, item_id: uuid.UUID, actor_user_id: uuid.UUID) -> BlueprintItem:
        """Approve an item as the AI proposed it."""
        item = await self._get_pending_item(item_id)
        return await self._claim_and_apply(
            item.id, actor_user_id, BlueprintStatus.APPROVED.value, item.title
        )

    async def edit_item(
        self, item_id: uuid.UUID, actor_user_id: uuid.UUID, new_title: str
    ) -> BlueprintItem:
        """Approve an item with HR's own wording."""
        item = await self._get_pending_item(item_id)
        return await self._claim_and_apply(
            item.id, actor_user_id, BlueprintStatus.EDITED.value, new_title.strip()
        )

    async def reject_item(self, item_id: uuid.UUID, actor_user_id: uuid.UUID) -> BlueprintItem:
        """Reject an item. Items that depended on it will refuse to apply later."""
        await self._get_pending_item(item_id)
        rejected = await self._repo.review_pending_item(
            item_id, actor_user_id, BlueprintStatus.REJECTED.value, None
        )
        if rejected is None:
            raise BlueprintItemAlreadyReviewedException()
        await self._audit.log_action(
            organization_id=rejected.organization_id,
            actor_user_id=actor_user_id,
            action="reject",
            entity_type="blueprint_item",
            entity_id=rejected.id,
            changes={
                "old": {"status": BlueprintStatus.PENDING.value},
                "new": {"status": BlueprintStatus.REJECTED.value},
            },
        )
        return rejected

    async def accept_all(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> AcceptAllResponse:
        """Approve every pending item, parents first; report the ones that could not be applied.

        Each item runs inside its own savepoint, so one that fails (say, a
        rename that clashes with an existing name) is undone alone and listed
        as skipped; everything else still goes through.
        """
        pending_items = await self._repo.list_pending_items(organization_id)
        # Plain (id, title, kind) values: after a savepoint rolls back, the loaded
        # objects can be stale, and reading them in an async session would fail.
        pending = [(item.id, item.title, item.kind) for item in pending_items]
        pending.sort(key=lambda row: KIND_ORDER.index(row[2]))
        pending_before = len(pending)

        skipped: list[AcceptAllSkipped] = []
        for item_id, item_title, _ in pending:
            current = await self._repo.get_item(item_id)
            if current.status != BlueprintStatus.PENDING.value:
                continue  # an earlier item already approved this one as its parent
            try:
                async with self._db.begin_nested():
                    await self._claim_and_apply(
                        item_id, actor_user_id, BlueprintStatus.APPROVED.value, item_title
                    )
            except PlatformError as error:
                skipped.append(
                    AcceptAllSkipped(id=item_id, title=item_title, reason=error.message)
                )

        still_pending = await self._repo.list_pending_items(organization_id)
        return AcceptAllResponse(
            accepted=pending_before - len(still_pending), skipped=skipped
        )
