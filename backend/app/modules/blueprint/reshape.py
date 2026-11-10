"""Reshape a plan that is still being reviewed: add a left-out item back, or merge two items.

Only PENDING items are touched, and nothing here creates a real department or
position: the owner still approves the result like any other item. Never commits:
the router owns the transaction.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BlueprintItemAlreadyReviewedException,
    BlueprintItemNotFoundException,
    ValidationException,
)

from app.modules.kpis.repository import KPIRepository

from .enums import BlueprintKind, BlueprintStatus
from .generation import _cut_reporting_loops, normalize_weights
from .models import BlueprintItem
from .repository import BlueprintRepository
from .service import BlueprintService


class BlueprintReshaper:
    """Turn a left-out item back into its own, or merge two suggested items into one."""

    def __init__(self, db: AsyncSession):
        """Initialize with an RLS-scoped session."""
        self._db = db
        self._repo = BlueprintRepository(db)

    async def _get_pending(self, item_id: uuid.UUID) -> BlueprintItem:
        """The item, or 404 if unseen, or 409 if it was already reviewed."""
        item = await self._repo.get_item(item_id)
        if item is None:
            raise BlueprintItemNotFoundException()
        if item.status != BlueprintStatus.PENDING.value:
            raise BlueprintItemAlreadyReviewedException()
        return item

    async def add_separately(self, item_id: uuid.UUID) -> BlueprintItem:
        """Turn a left-out item back into a normal pending department or role.

        A department comes back with no capital share (the others keep theirs). A role
        comes back in the department of whatever covered it, reporting to it; the owner
        can change both before adding it.
        """
        item = await self._get_pending(item_id)
        if item.kind != BlueprintKind.FOLDED.value:
            raise ValidationException(message="Only a left-out item can be added back as its own.")

        batch = await self._repo.list_batch_items(item.batch_id)
        host = next((i for i in batch if i.ref is not None and i.ref == item.folded_into_ref), None)

        # What was left out is the same kind of thing as what covers it.
        if host is not None:
            is_position = host.kind == BlueprintKind.POSITION.value
        else:
            is_position = item.position_id is not None
        new_ref = "U" + uuid.uuid4().hex[:8]

        if not is_position:
            item.kind = BlueprintKind.DEPARTMENT.value
            item.is_critical = False
            item.department_id = None
        else:
            await self._place_in_the_covering_roles_department(item, host)
            item.kind = BlueprintKind.POSITION.value
            item.is_critical = False
            item.position_id = None

        item.ref = new_ref
        item.folded_into_ref = None
        await self._db.flush()
        return item

    async def merge(self, source_id: uuid.UUID, target_id: uuid.UUID) -> BlueprintItem:
        """Leave ``source`` out of the plan and let ``target`` cover it.

        Both must be suggested (pending) items of the same plan and of the same kind,
        two departments or two roles. Everything that pointed at the source now points
        at the target. Returns the source, which has become a left-out note.
        """
        if source_id == target_id:
            raise ValidationException(message="Choose a different item to merge into.")
        source = await self._get_pending(source_id)
        target = await self._get_pending(target_id)
        mergeable_kinds = (BlueprintKind.DEPARTMENT.value, BlueprintKind.POSITION.value)
        if (
            source.batch_id != target.batch_id
            or source.kind != target.kind
            or source.kind not in mergeable_kinds
            or source.ref is None
            or target.ref is None
        ):
            raise ValidationException(
                message="Only two suggested departments, or two suggested roles, can be merged."
            )

        batch = await self._repo.list_batch_items(source.batch_id)
        others = [i for i in batch if i.id != source.id and i.id != target.id]
        if source.kind == BlueprintKind.DEPARTMENT.value:
            self._merge_departments(source, target, others)
        else:
            self._merge_positions(source, target, others)

        # Anything already left out because of the source is now covered by the target.
        for other in others:
            if other.kind == BlueprintKind.FOLDED.value and other.folded_into_ref == source.ref:
                other.folded_into_ref = target.ref
        self._turn_into_a_left_out_note(source, target.title, target.ref)
        await self._db.flush()
        return source

    async def merge_into_existing(
        self, source_id: uuid.UUID, existing_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> BlueprintItem:
        """Leave a suggested department or role out, covered by one the company already has.

        The suggested item has no employees (it is not real yet), so nothing real moves
        except the capital share and the KPI weights, which are kept consistent below.
        """
        source = await self._get_pending(source_id)
        if (
            source.kind not in (BlueprintKind.DEPARTMENT.value, BlueprintKind.POSITION.value)
            or source.ref is None
        ):
            raise ValidationException(message="Only a suggested department or role can be merged.")

        batch = await self._repo.list_batch_items(source.batch_id)
        others = [i for i in batch if i.id != source.id]
        if source.kind == BlueprintKind.DEPARTMENT.value:
            target_title, note = await self._merge_department_into_existing(
                source, existing_id, others, actor_user_id
            )
        else:
            target_title, note = await self._merge_position_into_existing(source, existing_id, others)

        # Anything already left out because of the source is now covered by the real row.
        for other in others:
            if other.kind == BlueprintKind.FOLDED.value and other.folded_into_ref == source.ref:
                other.folded_into_ref = None
                if source.kind == BlueprintKind.DEPARTMENT.value:
                    other.department_id = existing_id
                else:
                    other.position_id = existing_id
        self._turn_into_a_left_out_note(source, target_title, None, existing_id)
        if note:
            source.rationale = source.rationale + " " + note
        await self._db.flush()
        # The source's capital share is gone from the split: hand it on to the others
        # (and, for a real department that came from this plan, to that department).
        await BlueprintService(self._db)._rebalance_capital(source.batch_id, actor_user_id)
        return source

    async def _merge_department_into_existing(
        self,
        source: BlueprintItem,
        existing_id: uuid.UUID,
        others: list[BlueprintItem],
        actor_user_id: uuid.UUID,
    ) -> tuple[str, str]:
        """Move the suggested department's roles, objectives and KPIs onto a real department."""
        real = next(
            (d for d in await self._repo.list_existing_departments() if d.id == existing_id), None
        )
        if real is None:
            raise ValidationException(
                message="That department could not be found.", code="BLUEPRINT_TARGET_NOT_FOUND", status_code=404
            )
        for item in others:
            if item.department_ref == source.ref:
                item.department_ref = None
                item.department_id = real.id

        # If the real department came from this plan, its plan item is still what the other
        # suggested items point at (by label), and it takes the source's share of the capital.
        host_item = next(
            (
                i
                for i in others
                if i.kind == BlueprintKind.DEPARTMENT.value and i.created_entity_id == real.id
            ),
            None,
        )
        if (
            host_item is not None
            and host_item.revenue_allocation_pct is not None
            and source.revenue_allocation_pct is not None
        ):
            host_item.revenue_allocation_pct = host_item.revenue_allocation_pct + source.revenue_allocation_pct
        host_ref = host_item.ref if host_item is not None else None

        # The suggested KPIs must fit in the weight the real department has left (it may
        # already have KPIs of its own, which are never changed here).
        used = await KPIRepository(self._db).sum_weights_for_group(real.id)
        room = max(Decimal(100) - used, Decimal(0))
        kpis = [
            i
            for i in others
            if i.kind == BlueprintKind.KPI.value
            and i.status == BlueprintStatus.PENDING.value
            and (i.department_id == real.id or (host_ref is not None and i.department_ref == host_ref))
        ]
        note = ""
        if kpis and room > 0:
            new_weights = normalize_weights([float(k.kpi_weight) for k in kpis], room)
            for kpi, weight in zip(kpis, new_weights):
                kpi.kpi_weight = weight
        elif kpis:
            # No weight left: those KPIs could never be added, so they are set aside.
            for kpi in kpis:
                await self._repo.review_pending_item(kpi.id, actor_user_id, BlueprintStatus.REJECTED.value, None)
            note = real.name + " already has a full set of KPIs, so the suggested ones were set aside."
        return real.name, note

    async def _merge_position_into_existing(
        self, source: BlueprintItem, existing_id: uuid.UUID, others: list[BlueprintItem]
    ) -> tuple[str, str]:
        """Make the roles that reported to the suggested role report to a real role."""
        real = next((p for p in await self._repo.list_existing_positions() if p.id == existing_id), None)
        if real is None:
            raise ValidationException(
                message="That role could not be found.", code="BLUEPRINT_TARGET_NOT_FOUND", status_code=404
            )
        for item in others:
            if item.reports_to_ref == source.ref:
                item.reports_to_ref = None
                item.reports_to_position_id = real.id
        return real.title, ""

    def _merge_departments(
        self, source: BlueprintItem, target: BlueprintItem, others: list[BlueprintItem]
    ) -> None:
        """Move the source department's roles, objectives, KPIs and capital share to the target."""
        for item in others:
            if item.department_ref == source.ref:
                item.department_ref = target.ref

        # The capital stays split to 100: the target takes the source's share.
        if source.revenue_allocation_pct is not None:
            target.revenue_allocation_pct = (target.revenue_allocation_pct or Decimal("0")) + (
                source.revenue_allocation_pct
            )
        target.is_critical = bool(target.is_critical or source.is_critical)
        if target.profit_margin_pct is None:
            target.profit_margin_pct = source.profit_margin_pct

        # The KPIs of both are now one department's, whose weights must total 100 again.
        kpis = [
            i
            for i in others
            if i.kind == BlueprintKind.KPI.value
            and i.department_ref == target.ref
            and i.status == BlueprintStatus.PENDING.value
        ]
        if kpis:
            new_weights = normalize_weights([float(k.kpi_weight) for k in kpis], Decimal("100"))
            for kpi, weight in zip(kpis, new_weights):
                kpi.kpi_weight = weight

    def _merge_positions(
        self, source: BlueprintItem, target: BlueprintItem, others: list[BlueprintItem]
    ) -> None:
        """Make the target role cover the source: its reports now report to the target."""
        for item in others:
            if item.reports_to_ref == source.ref:
                item.reports_to_ref = target.ref
        # If the target reported to the source, it now answers to the source's own boss.
        if target.reports_to_ref == source.ref:
            target.reports_to_ref = source.reports_to_ref
            target.reports_to_position_id = source.reports_to_position_id
        if source.is_critical and not target.is_critical:
            target.is_critical = True
            target.criticality_type = source.criticality_type
            target.risk_level = source.risk_level

        # Re-pointing can close a loop (A to B to A): cut it, as generation does.
        with_a_boss = [
            p
            for p in others + [target]
            if p.kind == BlueprintKind.POSITION.value and p.ref is not None and p.reports_to_ref is not None
        ]
        boss_of = {p.ref: p.reports_to_ref for p in with_a_boss}
        _cut_reporting_loops(boss_of)
        for position in with_a_boss:
            if position.ref not in boss_of:
                position.reports_to_ref = None

    def _turn_into_a_left_out_note(
        self,
        source: BlueprintItem,
        target_title: str,
        target_ref: str | None,
        existing_id: uuid.UUID | None = None,
    ) -> None:
        """The merged item stops being a department or role and becomes a left-out note.

        What covers it is another item of the plan (``target_ref``) or a real department or
        position (``existing_id``): a left-out note points at a real row with the same
        ``department_id`` / ``position_id`` columns the AI's own notes use.
        """
        was_a_department = source.kind == BlueprintKind.DEPARTMENT.value
        source.kind = BlueprintKind.FOLDED.value
        source.folded_into_ref = target_ref
        source.rationale = "You merged this into " + target_title + "."
        source.ref = None
        source.department_ref = None
        source.department_id = None
        source.position_id = None
        source.reports_to_ref = None
        source.reports_to_position_id = None
        source.is_critical = None
        source.revenue_allocation_pct = None
        source.profit_margin_pct = None
        source.criticality_type = None
        source.risk_level = None
        if existing_id is not None and was_a_department:
            source.department_id = existing_id
        elif existing_id is not None:
            source.position_id = existing_id

    async def _place_in_the_covering_roles_department(
        self, item: BlueprintItem, host: BlueprintItem | None
    ) -> None:
        """Give a role that comes back its department and its boss: the role that covered it."""
        if host is not None:
            item.department_ref = host.department_ref
            item.department_id = host.department_id
            item.reports_to_ref = host.ref
            item.reports_to_position_id = None
            return
        # The cover is a position the company already has.
        existing = next(
            (p for p in await self._repo.list_existing_positions() if p.id == item.position_id), None
        )
        if existing is None:
            raise ValidationException(message="The role that covered this one could not be found.")
        item.department_ref = None
        item.department_id = existing.department_id
        item.reports_to_ref = None
        item.reports_to_position_id = existing.id
