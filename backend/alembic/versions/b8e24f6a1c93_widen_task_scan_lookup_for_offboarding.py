"""Widen the task scan's lookup so it also finds work left by offboarded employees.

The Task scan (every 10 minutes) now does two jobs per organization: announce
overdue tasks, and hand over the open tasks of employees who have been
offboarded (08_DECISIONS.md 2026-10-09). The lookup function that tells it
which organizations to look at therefore changes meaning, so it is replaced by
``organizations_needing_task_scan()`` and the old
``organizations_with_unannounced_overdue_tasks()`` is dropped. It is still the
Task module's one cross-tenant function (not an additional one): SECURITY
DEFINER, pinned search_path, EXECUTE granted to elevare_app only, organization
ids and nothing else.

An organization is returned when it has an open task that either
(a) is overdue under the block-aware rule and not yet announced, or
(b) is assigned to an employee whose status is 'inactive'.

Revision ID: b8e24f6a1c93
Revises: a3d9e61c7b25
Create Date: 2026-10-09 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8e24f6a1c93'
down_revision: Union[str, Sequence[str], None] = 'a3d9e61c7b25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the wider function, grant it, and drop the old one."""
    op.execute(
        """
        CREATE FUNCTION organizations_needing_task_scan()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT DISTINCT t.organization_id
            FROM tasks t
            WHERE t.deleted_at IS NULL
              AND t.status IN ('open', 'in_progress')
              AND (
                  (
                      t.due_at IS NOT NULL
                      AND t.blocked_since IS NULL
                      AND t.due_at + make_interval(secs => t.approved_blocked_seconds) < now()
                      AND t.overdue_notified_at IS NULL
                  )
                  OR t.assigned_to_employee_id IN (
                      SELECT e.id FROM employees e WHERE e.status = 'inactive'
                  )
              );
        $$
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION organizations_needing_task_scan() TO elevare_app")
    op.execute("DROP FUNCTION IF EXISTS organizations_with_unannounced_overdue_tasks()")


def downgrade() -> None:
    """Put back the previous function and drop the wider one."""
    op.execute(
        """
        CREATE FUNCTION organizations_with_unannounced_overdue_tasks()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT DISTINCT t.organization_id
            FROM tasks t
            WHERE t.deleted_at IS NULL
              AND t.status IN ('open', 'in_progress')
              AND t.due_at IS NOT NULL
              AND t.blocked_since IS NULL
              AND t.due_at + make_interval(secs => t.approved_blocked_seconds) < now()
              AND t.overdue_notified_at IS NULL;
        $$
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION organizations_with_unannounced_overdue_tasks() TO elevare_app"
    )
    op.execute("DROP FUNCTION IF EXISTS organizations_needing_task_scan()")
