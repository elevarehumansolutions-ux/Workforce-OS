"""Erasing a deleted company for good, 30 days after its owner deleted it (08_DECISIONS.md 2026-11-14).

Deleting a company only archives it (``organizations.archived_at``). This module is the second half:
once it has been archived for ``PURGE_AFTER_DAYS``, every row that belongs to it is removed.

Why the order is worked out at run time: 26 of the 27 foreign keys to ``organizations`` do not cascade,
and the tables point at each other (a role needs its department, an employee needs their role, and so
on). So the rows must be removed children first. The order is read from the database's own foreign-key
list, not written by hand, so a table added in the future is covered automatically. If the list ever
contains a loop this code does not know about, it refuses and deletes nothing.
"""

import logging
import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# How long a deleted company stays restorable. Shown to the owner on the screen as well.
PURGE_AFTER_DAYS = 30

# The one loop in the tables: a department points at its head (an employee), and an employee points at a
# role, which points at a department. It is broken by clearing the head first, then ignoring that arrow.
# (child table, parent table, column that is cleared)
KNOWN_LOOP = ("departments", "employees", "head_employee_id")

_SAFE_NAME = re.compile(r"^[a-z0-9_]+$")


def order_for_deletion(tables: list[str], arrows: list[tuple[str, str]]) -> list[str]:
    """Put tables in an order where each one is removed BEFORE the tables it points to.

    ``arrows`` are (child, parent) pairs: the child has a foreign key to the parent, so the child's
    rows must go first. A table pointing at itself (an employee's manager) is fine: all its rows go in
    one statement. Raises if the arrows contain a loop, so nothing half-deletes.
    """
    remaining = set(tables)
    order = []
    while remaining:
        # A table can go now if no table still waiting points at it.
        ready = []
        for table in sorted(remaining):
            still_pointing = [c for (c, p) in arrows if p == table and c in remaining and c != table]
            if not still_pointing:
                ready.append(table)
        if not ready:
            raise RuntimeError("Unknown loop between tables, refusing to purge: " + ", ".join(sorted(remaining)))
        for table in ready:
            order.append(table)
            remaining.remove(table)
    return order


async def tables_to_purge(db: AsyncSession) -> list[str]:
    """Every table that has an ``organization_id`` column, in the order their rows must be removed."""
    result = await db.execute(
        text(
            """
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND c.column_name = 'organization_id' AND t.table_type = 'BASE TABLE'
            """
        )
    )
    tables = [row.table_name for row in result]

    result = await db.execute(
        text(
            """
            SELECT child.relname AS child, parent.relname AS parent
            FROM pg_constraint con
            JOIN pg_class child ON child.oid = con.conrelid
            JOIN pg_class parent ON parent.oid = con.confrelid
            JOIN pg_namespace n ON n.oid = child.relnamespace
            WHERE con.contype = 'f' AND n.nspname = 'public'
            """
        )
    )
    arrows = [(row.child, row.parent) for row in result]
    # Only arrows between the company's own tables matter (the others point at users, which stay).
    arrows = [(c, p) for (c, p) in arrows if c in tables and p in tables]
    # The known loop is handled by clearing the head first, so that arrow is left out of the ordering.
    arrows = [(c, p) for (c, p) in arrows if (c, p) != (KNOWN_LOOP[0], KNOWN_LOOP[1])]

    for table in tables:
        if not _SAFE_NAME.match(table):
            raise RuntimeError("Unexpected table name, refusing to purge: " + table)
    return order_for_deletion(tables, arrows)


async def purge_company(
    db: AsyncSession, organization_id: uuid.UUID, retention_days: int = PURGE_AFTER_DAYS
) -> dict[str, int] | None:
    """Erase one deleted company and everything in it. Returns rows removed per table, or None if skipped.

    Skipped (nothing touched) when the company is gone already, was restored, or is not yet
    ``retention_days`` old. All or nothing: one transaction, so a failure leaves the company exactly as it was.
    People's own accounts are NOT touched; only their place in this company and its records go.
    """
    await db.execute(text("SELECT set_config('app.current_user_id', '', true)"))
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(organization_id)}
    )
    # Lock the company row and look again inside this transaction. A restore that lands at the same
    # moment waits for us, or is waited for, so a company is never half-restored and half-erased.
    row = (
        await db.execute(
            text(
                """
                SELECT archived_at IS NOT NULL AND archived_at < now() - make_interval(days => :days) AS due
                FROM organizations WHERE id = :id FOR UPDATE
                """
            ),
            {"id": organization_id, "days": retention_days},
        )
    ).first()
    if row is None or not row.due:
        # Nothing was changed; the caller's session closing releases the row lock.
        return None

    order = await tables_to_purge(db)

    # Clear the department heads first (the one known loop), then remove children before parents.
    loop_table, _, loop_column = KNOWN_LOOP
    await db.execute(
        text(f'UPDATE "{loop_table}" SET "{loop_column}" = NULL WHERE organization_id = :id'), {"id": organization_id}
    )
    removed = {}
    for table in order:
        result = await db.execute(text(f'DELETE FROM "{table}" WHERE organization_id = :id'), {"id": organization_id})
        removed[table] = result.rowcount
    result = await db.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": organization_id})
    if result.rowcount != 1:
        raise RuntimeError("The company row was not removed, rolling the purge back")
    await db.commit()

    logger.info(
        "Deleted company erased",
        extra={"organization_id": str(organization_id), "rows_removed": sum(removed.values())},
    )
    return removed


async def list_due_for_purge(db: AsyncSession, retention_days: int = PURGE_AFTER_DAYS) -> list[uuid.UUID]:
    """The ids of deleted companies old enough to erase (the one cross-company read of this job)."""
    result = await db.execute(
        text("SELECT organization_id FROM organizations_due_for_purge(:days)"), {"days": retention_days}
    )
    return [row.organization_id for row in result]
