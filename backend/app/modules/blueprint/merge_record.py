"""Remember what a merge changed on the plan's items, and put it back.

A merge rewrites several waiting items at once (the merged one becomes a left-out note, its roles
and KPIs move, capital shares and weights are re-spread). To reverse it exactly, the merge takes a
snapshot of the columns it may touch before it starts, and afterwards keeps the OLD value of every
column that changed. Undoing puts those old values back. Plain data only (strings and numbers),
because it is stored as JSON.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from .models import BlueprintItem

# Every column a merge (or the capital and weight spreading that comes with it) can change.
MERGE_COLUMNS = [
    "kind",
    "ref",
    "folded_into_ref",
    "rationale",
    "department_id",
    "department_ref",
    "position_id",
    "reports_to_position_id",
    "reports_to_ref",
    "is_critical",
    "revenue_allocation_pct",
    "profit_margin_pct",
    "criticality_type",
    "risk_level",
    "kpi_weight",
    "status",
    "reviewed_title",
    "reviewed_by_user_id",
    "reviewed_at",
]

# How to turn the stored text back into the column's own type.
_UUID_COLUMNS = {"department_id", "position_id", "reports_to_position_id", "reviewed_by_user_id"}
_DECIMAL_COLUMNS = {"revenue_allocation_pct", "profit_margin_pct", "kpi_weight"}
_DATETIME_COLUMNS = {"reviewed_at"}


def _to_plain(value):
    """A column value as something JSON can hold."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _from_plain(column: str, value):
    """The stored text turned back into the column's type."""
    if value is None:
        return None
    if column in _UUID_COLUMNS:
        return uuid.UUID(value)
    if column in _DECIMAL_COLUMNS:
        return Decimal(value)
    if column in _DATETIME_COLUMNS:
        return datetime.fromisoformat(value)
    return value


def take_snapshot(items: list[BlueprintItem]) -> dict[str, dict]:
    """{item id: {column: value}} for every item, as plain data."""
    snapshot: dict[str, dict] = {}
    for item in items:
        snapshot[str(item.id)] = {column: _to_plain(getattr(item, column)) for column in MERGE_COLUMNS}
    return snapshot


def changes_since(before: dict[str, dict], items: list[BlueprintItem]) -> dict[str, dict]:
    """{item id: {column: OLD value}} for only the columns that differ from the snapshot."""
    changed: dict[str, dict] = {}
    for item in items:
        old_values = before.get(str(item.id))
        if old_values is None:
            continue
        differences = {}
        for column in MERGE_COLUMNS:
            if _to_plain(getattr(item, column)) != old_values[column]:
                differences[column] = old_values[column]
        if differences:
            changed[str(item.id)] = differences
    return changed


def restore(item: BlueprintItem, old_values: dict) -> None:
    """Put the remembered old values back on an item."""
    for column, value in old_values.items():
        setattr(item, column, _from_plain(column, value))
