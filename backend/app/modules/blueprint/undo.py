"""Undo an item that was already added: remove the real row and put the plan item back to waiting.

Undoing a department, role, objective or key result also removes everything that was added
under it from the same plan (the owner is warned first, with a count, see ``preview``). It
goes through the other modules' own delete rules, so if one of them refuses (a person still
holds the role, a task still points at it) the whole undo is refused with its reason and
nothing changes: the router does not commit, so everything done before the refusal is
rolled back. Never commits.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BlueprintItemNotFoundException,
    DepartmentNotFoundException,
    KeyResultNotFoundException,
    KPINotFoundException,
    OKRNotFoundException,
    PositionNotFoundException,
    ResourceInUseException,
    ValidationException,
)
from app.modules.audit_and_notification.service import AuditService
from app.modules.kpis.service import KPIService
from app.modules.okrs.service import KeyResultService, OKRService
from app.modules.organization.service import DepartmentService, PositionService

from .enums import BlueprintKind, BlueprintStatus
from .models import BlueprintItem
from .repository import BlueprintRepository
from .service import BlueprintService

# The kinds that become a real row and can therefore be undone.
UNDOABLE_KINDS = (
    BlueprintKind.DEPARTMENT.value,
    BlueprintKind.POSITION.value,
    BlueprintKind.OBJECTIVE.value,
    BlueprintKind.KEY_RESULT.value,
    BlueprintKind.KPI.value,
)

# The order real rows are removed in: the smallest things first, the department last.
REMOVAL_ORDER = [
    BlueprintKind.KPI.value,
    BlueprintKind.KEY_RESULT.value,
    BlueprintKind.OBJECTIVE.value,
    BlueprintKind.POSITION.value,
    BlueprintKind.DEPARTMENT.value,
]


def is_added(item: BlueprintItem) -> bool:
    """True when the item became a real row (approved or edited, and the row is known)."""
    added_status = item.status in (BlueprintStatus.APPROVED.value, BlueprintStatus.EDITED.value)
    return added_status and item.created_entity_id is not None


def things_directly_under(item: BlueprintItem, candidate: BlueprintItem) -> bool:
    """True when ``candidate`` was added under ``item``: it points at it by ref or by real id."""
    if item.kind == BlueprintKind.DEPARTMENT.value:
        if candidate.kind not in (
            BlueprintKind.POSITION.value,
            BlueprintKind.OBJECTIVE.value,
            BlueprintKind.KPI.value,
        ):
            return False
        by_ref = item.ref is not None and candidate.department_ref == item.ref
        by_id = candidate.department_id == item.created_entity_id
        return by_ref or by_id

    if item.kind == BlueprintKind.POSITION.value:
        if candidate.kind != BlueprintKind.POSITION.value:
            return False
        by_ref = item.ref is not None and candidate.reports_to_ref == item.ref
        by_id = candidate.reports_to_position_id == item.created_entity_id
        return by_ref or by_id

    if item.kind == BlueprintKind.OBJECTIVE.value:
        return (
            candidate.kind == BlueprintKind.KEY_RESULT.value
            and item.ref is not None
            and candidate.objective_ref == item.ref
        )

    if item.kind == BlueprintKind.KEY_RESULT.value:
        return (
            candidate.kind == BlueprintKind.KPI.value
            and item.ref is not None
            and candidate.key_result_ref == item.ref
        )

    return False


def everything_added_under(item: BlueprintItem, batch: list[BlueprintItem]) -> list[BlueprintItem]:
    """All items of the plan added under ``item``, at any depth (the item itself is not included).

    Walks down level by level: a department's roles, a role's own reports, an objective's key
    results, a key result's KPIs. Only things that are really added are returned: ones still
    waiting have nothing to remove.
    """
    found: list[BlueprintItem] = []
    seen_ids = {item.id}
    to_visit = [item]
    while to_visit:
        parent = to_visit.pop()
        for candidate in batch:
            if candidate.id in seen_ids or not is_added(candidate):
                continue
            if things_directly_under(parent, candidate):
                seen_ids.add(candidate.id)
                found.append(candidate)
                to_visit.append(candidate)
    return found


def removal_order(items: list[BlueprintItem]) -> list[BlueprintItem]:
    """Put the items in the order their real rows must be removed.

    By kind first (KPIs, key results, objectives, roles, departments). Among roles, a role goes
    before the role it reports to, because a role cannot be deleted while others report to it.
    """
    ordered: list[BlueprintItem] = []
    for kind in REMOVAL_ORDER:
        of_kind = [item for item in items if item.kind == kind]
        if kind != BlueprintKind.POSITION.value:
            ordered.extend(of_kind)
            continue
        # Roles: repeatedly take the ones no other remaining role reports to.
        remaining = list(of_kind)
        while remaining:
            bosses_still_needed = {
                other.reports_to_ref for other in remaining if other.reports_to_ref is not None
            }
            leaves = [item for item in remaining if item.ref not in bosses_still_needed]
            if not leaves:
                leaves = list(remaining)  # a loop in the data: do not spin forever
            ordered.extend(leaves)
            remaining = [item for item in remaining if item not in leaves]
    return ordered


class BlueprintUndo:
    """Warn about, then carry out, the undoing of an item that was already added."""

    def __init__(self, db: AsyncSession):
        """Initialize with an RLS-scoped session and the services that own the real rows."""
        self._db = db
        self._repo = BlueprintRepository(db)
        self._audit = AuditService(db)
        self._departments = DepartmentService(db)
        self._positions = PositionService(db)
        self._okrs = OKRService(db)
        self._key_results = KeyResultService(db)
        self._kpis = KPIService(db)

    async def _get_added_item(self, item_id: uuid.UUID) -> BlueprintItem:
        """The item, if it can be undone: 404 if unseen, 422 if it was never added or has no real row."""
        item = await self._repo.get_item(item_id)
        if item is None:
            raise BlueprintItemNotFoundException()
        if item.kind not in UNDOABLE_KINDS:
            raise ValidationException(message="This kind of item cannot be undone here.")
        if not is_added(item):
            raise ValidationException(message="This item has not been added, so there is nothing to undo.")
        return item

    async def preview(self, item_id: uuid.UUID) -> tuple[BlueprintItem, dict[str, int]]:
        """The item and how many of each kind would be removed with it (not counting itself)."""
        item = await self._get_added_item(item_id)
        batch = await self._repo.list_batch_items(item.batch_id)
        counts: dict[str, int] = {}
        for other in everything_added_under(item, batch):
            counts[other.kind] = counts.get(other.kind, 0) + 1
        return item, counts

    async def _remove_real_row(self, item: BlueprintItem, actor_user_id: uuid.UUID) -> None:
        """Delete the real row behind an item, through the module that owns it.

        A row that is already gone (someone deleted it elsewhere) is fine: the goal is that it
        no longer exists. Any other refusal (people still in the role, a task pointing at it)
        is passed on to the user as it is.
        """
        row_id = item.created_entity_id
        try:
            if item.kind == BlueprintKind.DEPARTMENT.value:
                await self._check_nothing_made_by_hand_remains(row_id)
                await self._departments.delete_department(row_id, actor_user_id)
            elif item.kind == BlueprintKind.POSITION.value:
                await self._positions.delete_position(row_id, actor_user_id)
            elif item.kind == BlueprintKind.OBJECTIVE.value:
                await self._okrs.delete_okr(row_id, actor_user_id)
            elif item.kind == BlueprintKind.KEY_RESULT.value:
                await self._key_results.delete_key_result(row_id, actor_user_id)
            elif item.kind == BlueprintKind.KPI.value:
                await self._remove_kpi(row_id, actor_user_id, item.organization_id)
        except (
            DepartmentNotFoundException,
            PositionNotFoundException,
            OKRNotFoundException,
            KeyResultNotFoundException,
            KPINotFoundException,
        ):
            return

    async def _check_nothing_made_by_hand_remains(self, department_id: uuid.UUID) -> None:
        """A department with KPIs or objectives of its own would leave them behind: refuse.

        Called after the plan's own KPIs and objectives were removed, so anything still alive
        was made by hand. The Organization module only checks roles, so this is checked here.
        """
        kpis = await self._repo.count_live_kpis_of_department(department_id)
        objectives = await self._repo.count_live_objectives_of_department(department_id)
        reasons = []
        if kpis > 0:
            reasons.append(f"{kpis} KPI(s) added by hand still belong to it")
        if objectives > 0:
            reasons.append(f"{objectives} objective(s) added by hand still belong to it")
        if reasons:
            raise ResourceInUseException(message=f"Cannot undo this department: {'; '.join(reasons)}")

    async def _remove_kpi(
        self, kpi_id: uuid.UUID, actor_user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Soft-delete one KPI and write the audit entry (the KPI service only deletes in groups)."""
        kpi = await self._kpis.kpi_repo.get_kpi_by_id(kpi_id)
        if kpi is None:
            raise KPINotFoundException(f"KPI {kpi_id} not found")
        name = kpi.name
        weight = str(kpi.weight)
        await self._kpis.kpi_repo.soft_delete_kpi(kpi)
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="kpi",
            entity_id=kpi_id,
            changes={"old": {"name": name, "weight": weight}, "new": None},
        )

    def _back_to_waiting(self, item: BlueprintItem) -> None:
        """Make an added item a suggestion again, keeping the wording the owner chose."""
        if item.reviewed_title:
            item.title = item.reviewed_title
        item.status = BlueprintStatus.PENDING.value
        item.reviewed_title = None
        item.reviewed_by_user_id = None
        item.reviewed_at = None
        item.created_entity_id = None

    async def undo(self, item_id: uuid.UUID, actor_user_id: uuid.UUID) -> int:
        """Undo an added item and everything added under it. Returns how many plan items went back.

        All or nothing: if any real row cannot be removed, the error is raised, the router does
        not commit, and nothing changes.
        """
        item = await self._get_added_item(item_id)
        batch = await self._repo.list_batch_items(item.batch_id)
        affected = removal_order(everything_added_under(item, batch) + [item])

        # A savepoint, so a refusal half way undoes the removals made before it, whatever the
        # caller does with the outer transaction.
        async with self._db.begin_nested():
            for one in affected:
                await self._remove_real_row(one, actor_user_id)
            for one in affected:
                self._back_to_waiting(one)
                await self._audit.log_action(
                    organization_id=one.organization_id,
                    actor_user_id=actor_user_id,
                    action="undo",
                    entity_type="blueprint_item",
                    entity_id=one.id,
                    changes={
                        "old": {"status": BlueprintStatus.APPROVED.value},
                        "new": {"status": BlueprintStatus.PENDING.value},
                    },
                )
            await self._db.flush()

        # A department that is waiting again takes its share of the capital back into the split.
        await BlueprintService(self._db)._rebalance_capital(item.batch_id, actor_user_id)
        return len(affected)
