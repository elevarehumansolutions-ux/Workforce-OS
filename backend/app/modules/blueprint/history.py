"""The change history of the plan review: every change can be undone, then redone.

While the owner reviews the plan (the onboarding screens) each change they make (add, add with
their own wording, skip, merge, add a left-out item back, add everything) is recorded with the old
and the new value of every plan item it touched. Undo removes the real rows that change created
(through the same delete rules the per-item Undo uses) and puts the old values back. Redo runs the
same change again from what was recorded. Never commits: the router owns the transaction.

Plain on purpose: values are turned into text for storage with two small functions, and "is it
still as that change left it?" is a column-by-column comparison, not a clever diff.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BlueprintActionNotFoundException, BlueprintHistoryBlockedException
from app.modules.audit_and_notification.service import AuditService
from app.modules.organization.service import DepartmentService, PositionService

from .enums import BlueprintKind, BlueprintStatus
from .merge_record import MERGE_COLUMNS
from .models import BlueprintAction, BlueprintItem
from .repository import BlueprintRepository
from .reshape import BlueprintReshaper
from .service import BlueprintService
from .undo import BlueprintUndo, everything_added_under, removal_order

# Everything a review change can touch on an item: the columns a merge already tracks, plus the
# wording and the KPI details an edit changes, the real row an item became, and the merge note.
HISTORY_COLUMNS = MERGE_COLUMNS + [
    "title",
    "kpi_target_value",
    "kpi_unit",
    "kpi_is_inverse",
    "created_entity_id",
    "merge_record",
]

_UUID_COLUMNS = {
    "department_id",
    "position_id",
    "reports_to_position_id",
    "reviewed_by_user_id",
    "created_entity_id",
}
_DECIMAL_COLUMNS = {"revenue_allocation_pct", "profit_margin_pct", "kpi_weight", "kpi_target_value"}
_DATETIME_COLUMNS = {"reviewed_at"}

# How many changes the history keeps (older ones are dropped when a new one is recorded).
KEEP_LAST = 20


def to_plain(value):
    """A column value as something JSON can hold."""
    if value is None or isinstance(value, (bool, int, str, dict)):
        return value
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def from_plain(column: str, value):
    """The stored text turned back into the column's own type."""
    if value is None:
        return None
    if column in _UUID_COLUMNS:
        return uuid.UUID(value)
    if column in _DECIMAL_COLUMNS:
        return Decimal(value)
    if column in _DATETIME_COLUMNS:
        return datetime.fromisoformat(value)
    return value


def same_value(column: str, first, second) -> bool:
    """Are two stored values the same? Numbers compare as numbers ("20.0" is "20.00")."""
    if first is None or second is None:
        return first is None and second is None
    if column in _DECIMAL_COLUMNS:
        return Decimal(first) == Decimal(second)
    if column in _DATETIME_COLUMNS:
        return datetime.fromisoformat(first) == datetime.fromisoformat(second)
    return first == second


def take_snapshot(items: list[BlueprintItem]) -> dict[str, dict]:
    """{item id: {column: value}} for every item, as plain data."""
    snapshot: dict[str, dict] = {}
    for item in items:
        snapshot[str(item.id)] = {column: to_plain(getattr(item, column)) for column in HISTORY_COLUMNS}
    return snapshot


def find_changes(before: dict[str, dict], items: list[BlueprintItem]) -> dict[str, dict]:
    """{item id: {column: [old, new]}} for only the columns that differ from the snapshot."""
    changed: dict[str, dict] = {}
    for item in items:
        old_values = before.get(str(item.id))
        if old_values is None:
            continue  # an item made after the snapshot: no review change creates items
        differences = {}
        for column in HISTORY_COLUMNS:
            new_value = to_plain(getattr(item, column))
            if not same_value(column, old_values[column], new_value):
                differences[column] = [old_values[column], new_value]
        if differences:
            changed[str(item.id)] = differences
    return changed


def is_in_state(changes: dict[str, dict], items_by_id: dict[str, BlueprintItem], which: int) -> bool:
    """True when every item a change touched still holds that change's old (0) or new (1) values."""
    for item_id, columns in changes.items():
        item = items_by_id.get(item_id)
        if item is None:
            return False
        for column, pair in columns.items():
            if not same_value(column, pair[which], to_plain(getattr(item, column))):
                return False
    return True


def put_back(item: BlueprintItem, columns: dict[str, list]) -> None:
    """Give an item its old values back (the first of each [old, new] pair)."""
    for column, pair in columns.items():
        setattr(item, column, from_plain(column, pair[0]))


def moment() -> datetime:
    """Now, with a timezone (the one place this module reads the clock)."""
    return datetime.now(UTC)

# --- end of the plain helpers ---

# What an item is called in a history line ("department", "role", ...).
_NOUNS = {
    BlueprintKind.DEPARTMENT.value: "department",
    BlueprintKind.POSITION.value: "role",
    BlueprintKind.OBJECTIVE.value: "objective",
    BlueprintKind.KEY_RESULT.value: "key result",
    BlueprintKind.KPI.value: "KPI",
    BlueprintKind.RENAME_DEPARTMENT.value: "department",
    BlueprintKind.RENAME_POSITION.value: "role",
    BlueprintKind.REVIEW_NOTE.value: "note",
    BlueprintKind.FOLDED.value: "left-out item",
}
_RENAMES = (BlueprintKind.RENAME_DEPARTMENT.value, BlueprintKind.RENAME_POSITION.value)


class ReviewMark:
    """What the plan looked like just before a change: taken first, used to record the change after."""

    def __init__(self, organization_id: uuid.UUID, before: dict[str, dict], real_names: dict[str, str]):
        """Keep the snapshot and the real names that pending renames will overwrite."""
        self.organization_id = organization_id
        self.before = before
        self.real_names = real_names


class BlueprintHistory:
    """Record the owner's changes to the plan, and undo or redo them."""

    def __init__(self, db: AsyncSession):
        """Initialize with an RLS-scoped session and the services that own the real rows."""
        self._db = db
        self._repo = BlueprintRepository(db)
        self._audit = AuditService(db)
        self._departments = DepartmentService(db)
        self._positions = PositionService(db)

    # -- recording ---------------------------------------------------------------

    async def begin(self, organization_id: uuid.UUID) -> ReviewMark:
        """Take the "before" picture. Call this first, then make the change, then ``record``."""
        items = await self._repo.list_all_items(organization_id)
        real_names: dict[str, str] = {}
        pending_renames = [
            item for item in items if item.kind in _RENAMES and item.status == BlueprintStatus.PENDING.value
        ]
        if pending_renames:
            # A rename overwrites a real name; remember the old one so undo can put it back.
            department_names = {d.id: d.name for d in await self._repo.list_existing_departments()}
            position_titles = {p.id: p.title for p in await self._repo.list_existing_positions()}
            for item in pending_renames:
                if item.kind == BlueprintKind.RENAME_DEPARTMENT.value:
                    old_name = department_names.get(item.department_id)
                else:
                    old_name = position_titles.get(item.position_id)
                if old_name is not None:
                    real_names[str(item.id)] = old_name
        return ReviewMark(organization_id, take_snapshot(items), real_names)

    def _named(self, mark: ReviewMark, item_id: uuid.UUID) -> str:
        """'department "Sales"' for an item, as it was before the change."""
        was = mark.before[str(item_id)]
        return _NOUNS.get(was["kind"], "item") + ' "' + was["title"] + '"'

    def label_for_add(self, mark: ReviewMark, item_id: uuid.UUID, new_title: str | None = None) -> str:
        """The history line for adding an item as suggested, or with the owner's own wording."""
        was = mark.before[str(item_id)]
        if was["kind"] in _RENAMES:
            old_name = mark.real_names.get(str(item_id), was["title"])
            return 'Renamed "' + old_name + '" to "' + (new_title or was["title"]) + '"'
        if new_title is not None and new_title != was["title"]:
            return "Added " + _NOUNS.get(was["kind"], "item") + ' "' + new_title + '" (suggested as "' + was["title"] + '")'
        return "Added " + self._named(mark, item_id)

    def label_for_add_back(self, mark: ReviewMark, item: BlueprintItem) -> str:
        """The history line for turning a left-out item back into its own department or role."""
        was = mark.before[str(item.id)]
        return 'Added "' + was["title"] + '" back as its own ' + _NOUNS.get(item.kind, "item")

    def label_for_skip(self, mark: ReviewMark, item_id: uuid.UUID) -> str:
        """The history line for skipping an item."""
        return "Skipped " + self._named(mark, item_id)

    async def label_for_merge(
        self,
        mark: ReviewMark,
        source_id: uuid.UUID,
        target_id: uuid.UUID | None,
        existing_id: uuid.UUID | None,
    ) -> str:
        """The history line for merging one department or role into another."""
        if target_id is not None:
            target_name = mark.before[str(target_id)]["title"]
        elif existing_id is not None:
            target_name = "an existing one"
            for row in await self._repo.list_existing_departments():
                if row.id == existing_id:
                    target_name = row.name
            for row in await self._repo.list_existing_positions():
                if row.id == existing_id:
                    target_name = row.title
        else:
            target_name = "another one"
        return "Merged " + self._named(mark, source_id) + ' into "' + target_name + '"'

    async def record(
        self,
        mark: ReviewMark,
        actor_user_id: uuid.UUID,
        kind: str,
        label: str,
        params: dict,
    ) -> BlueprintAction | None:
        """Save the change that was just made. Returns None when it changed nothing worth keeping.

        A new change ends the redo list: the undone changes are forgotten, because redoing them on
        top of something new could put the plan in a state nobody chose. Only the last
        ``KEEP_LAST`` changes are kept.
        """
        items = await self._repo.list_all_items(mark.organization_id)
        changes = find_changes(mark.before, items)
        if not changes:
            return None

        existing = await self._repo.list_actions(mark.organization_id)
        forgotten = [a for a in existing if a.undone_at is not None]
        still_done = [a for a in existing if a.undone_at is None]  # newest first
        forgotten += still_done[KEEP_LAST - 1 :]  # room for the one being added
        await self._repo.delete_actions(forgotten)

        action = BlueprintAction(
            organization_id=mark.organization_id,
            created_by_user_id=actor_user_id,
            kind=kind,
            label=label,
            params=params,
            changes=changes,
            real_names=mark.real_names,
            # The clock, not the database's now(): that is the start of the transaction, so two
            # changes made in one transaction would tie and their order would be a guess.
            created_at=moment(),
        )
        return await self._repo.add_action(action)

    # -- reading -------------------------------------------------------------------

    def _later_change_touching(self, action: BlueprintAction, item_ids: set[str], actions: list[BlueprintAction]):
        """The newest later, not-undone change that touched any of these items, or None."""
        for other in actions:  # newest first
            if other.id == action.id or other.undone_at is not None:
                continue
            if other.created_at <= action.created_at:
                continue
            if item_ids & set(other.changes.keys()):
                return other
        return None

    def _blocked_reason(
        self,
        action: BlueprintAction,
        items_by_id: dict[str, BlueprintItem],
        actions: list[BlueprintAction],
    ) -> str | None:
        """Why this change cannot be undone now, in words for the owner, or None when it can."""
        if not is_in_state(action.changes, items_by_id, 1):
            if is_in_state(action.changes, items_by_id, 0):
                return "Already undone with the Undo button on the card."
            later = self._later_change_touching(action, set(action.changes.keys()), actions)
            if later is not None:
                return 'Undo "' + later.label + '" first.'
            return "The plan was changed after this, outside the history, so it cannot be undone here."

        # Removing what this change added must not take with it something a LATER change added under it.
        batch_items: dict[uuid.UUID, list[BlueprintItem]] = {}
        for item in items_by_id.values():
            batch_items.setdefault(item.batch_id, []).append(item)
        for item_id in self._items_added_by(action):
            item = items_by_id[item_id]
            for under in everything_added_under(item, batch_items[item.batch_id]):
                if str(under.id) in action.changes:
                    continue
                later = self._later_change_touching(action, {str(under.id)}, actions)
                if later is not None:
                    return 'Undo "' + later.label + '" first.'
                return "Something was added under this separately, so it has to be undone first."
        return None

    def _items_added_by(self, action: BlueprintAction) -> list[str]:
        """Ids of the items that became a real row because of this change."""
        added = []
        for item_id, columns in action.changes.items():
            pair = columns.get("created_entity_id")
            if pair is not None and pair[0] is None and pair[1] is not None:
                added.append(item_id)
        return added

    async def list_entries(self, organization_id: uuid.UUID) -> list[dict]:
        """The history, newest first, each with what the owner may do with it."""
        actions = await self._repo.list_actions(organization_id)
        items_by_id = {str(i.id): i for i in await self._repo.list_all_items(organization_id)}
        undone = [a for a in actions if a.undone_at is not None]
        next_to_redo = max(undone, key=lambda a: a.undone_at) if undone else None

        entries = []
        for action in actions:
            entry = {
                "id": action.id,
                "kind": action.kind,
                "label": action.label,
                "created_at": action.created_at,
                "state": "done",
                "can_undo": False,
                "can_redo": False,
                "reason": None,
            }
            if action.undone_at is not None:
                entry["state"] = "undone"
                if next_to_redo is not None and action.id == next_to_redo.id:
                    entry["can_redo"] = True
                else:
                    entry["reason"] = 'Redo "' + next_to_redo.label + '" first.'
            else:
                reason = self._blocked_reason(action, items_by_id, actions)
                if reason is None:
                    entry["can_undo"] = True
                else:
                    entry["reason"] = reason
                    if reason.startswith("Already undone"):
                        entry["state"] = "already_undone"
            entries.append(entry)
        return entries

    async def _get(self, action_id: uuid.UUID) -> BlueprintAction:
        """The recorded change, or 404."""
        action = await self._repo.get_action(action_id)
        if action is None:
            raise BlueprintActionNotFoundException()
        return action

    # -- undo and redo ------------------------------------------------------------

    async def undo(self, action_id: uuid.UUID, actor_user_id: uuid.UUID) -> BlueprintAction:
        """Take a change back: remove the real rows it created, then put the old values back.

        All or nothing: if another module refuses a removal (a person already holds the role) the
        error is raised, the savepoint undoes the part done, and nothing changes.
        """
        action = await self._get(action_id)
        if action.undone_at is not None:
            raise BlueprintHistoryBlockedException(message="This change is already undone.")
        organization_id = action.organization_id
        actions = await self._repo.list_actions(organization_id)
        items_by_id = {str(i.id): i for i in await self._repo.list_all_items(organization_id)}
        reason = self._blocked_reason(action, items_by_id, actions)
        if reason is not None:
            raise BlueprintHistoryBlockedException(message=reason)

        added = [items_by_id[item_id] for item_id in self._items_added_by(action)]
        batch_ids = {item.batch_id for item in (items_by_id[i] for i in action.changes)}
        remover = BlueprintUndo(self._db)
        async with self._db.begin_nested():
            # Real rows first, while each item still knows which row it became.
            for item in removal_order(added):
                await remover._remove_real_row(item, actor_user_id)
            for item_id, columns in action.changes.items():
                put_back(items_by_id[item_id], columns)
            await self._put_real_names_back(action, items_by_id, actor_user_id)
            await self._db.flush()
        for batch_id in batch_ids:
            # A department that is waiting again takes its share of the capital back into the split.
            await BlueprintService(self._db)._rebalance_capital(batch_id, actor_user_id)

        action.undone_at = moment()
        await self._audit_change("undo", action, actor_user_id)
        await self._db.flush()
        return action

    async def _put_real_names_back(
        self, action: BlueprintAction, items_by_id: dict[str, BlueprintItem], actor_user_id: uuid.UUID
    ) -> None:
        """A rename that was added overwrote a real department or role name: set the old one back."""
        for item_id, old_name in action.real_names.items():
            columns = action.changes.get(item_id)
            if columns is None or "status" not in columns:
                continue  # this change did not apply that rename
            item = items_by_id[item_id]
            if item.kind == BlueprintKind.RENAME_DEPARTMENT.value:
                await self._departments.update_department(item.department_id, actor_user_id, {"name": old_name})
            else:
                await self._positions.update_position(item.position_id, actor_user_id, {"title": old_name})

    async def redo(self, action_id: uuid.UUID, actor_user_id: uuid.UUID) -> BlueprintAction:
        """Do an undone change again, the same way it was done the first time."""
        action = await self._get(action_id)
        if action.undone_at is None:
            raise BlueprintHistoryBlockedException(message="This change is not undone, so there is nothing to redo.")
        organization_id = action.organization_id
        undone = [a for a in await self._repo.list_actions(organization_id) if a.undone_at is not None]
        newest = max(undone, key=lambda a: a.undone_at)
        if newest.id != action.id:
            raise BlueprintHistoryBlockedException(message='Redo "' + newest.label + '" first.')

        mark = await self.begin(organization_id)
        async with self._db.begin_nested():
            await self._run_again(action, actor_user_id)
        items = await self._repo.list_all_items(organization_id)
        action.changes = find_changes(mark.before, items)
        action.real_names = mark.real_names
        action.undone_at = None
        await self._audit_change("redo", action, actor_user_id)
        await self._db.flush()
        return action

    async def _run_again(self, action: BlueprintAction, actor_user_id: uuid.UUID) -> None:
        """Run the recorded change again with what was recorded."""
        p = action.params
        service = BlueprintService(self._db)
        if action.kind == "approve":
            await service.approve_item(uuid.UUID(p["item_id"]), actor_user_id)
        elif action.kind == "edit":
            details = details_from_plain(p.get("details") or {})
            await service.edit_item(uuid.UUID(p["item_id"]), actor_user_id, p["title"], details)
        elif action.kind == "reject":
            await service.reject_item(uuid.UUID(p["item_id"]), actor_user_id)
        elif action.kind == "add_separately":
            await BlueprintReshaper(self._db).add_separately(uuid.UUID(p["item_id"]))
        elif action.kind == "merge":
            if p.get("target_id"):
                await BlueprintReshaper(self._db).merge(uuid.UUID(p["item_id"]), uuid.UUID(p["target_id"]))
            else:
                await BlueprintReshaper(self._db).merge_into_existing(
                    uuid.UUID(p["item_id"]), uuid.UUID(p["existing_id"]), actor_user_id
                )
        elif action.kind == "accept_all":
            await service.accept_all(action.organization_id, actor_user_id)

    async def _audit_change(self, verb: str, action: BlueprintAction, actor_user_id: uuid.UUID) -> None:
        """One audit line for an undo or a redo, naming the change."""
        any_item_id = uuid.UUID(next(iter(action.changes)))
        await self._audit.log_action(
            organization_id=action.organization_id,
            actor_user_id=actor_user_id,
            action=verb,
            entity_type="blueprint_item",
            entity_id=any_item_id,
            changes={"old": None, "new": {"change": action.label}},
        )


def details_from_plain(details: dict) -> dict:
    """Edit details as stored (text) turned back into numbers for the edit rules."""
    numbers = {"kpi_weight", "kpi_target_value", "revenue_allocation_pct", "profit_margin_pct"}
    back = {}
    for key, value in details.items():
        back[key] = Decimal(value) if key in numbers and value is not None else value
    return back


def details_to_plain(details: dict) -> dict:
    """Edit details turned into text, so they can be stored and run again later."""
    return {key: to_plain(value) for key, value in details.items()}

# --- end of history ---
