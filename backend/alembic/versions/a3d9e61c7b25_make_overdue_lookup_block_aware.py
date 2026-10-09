"""Make the overdue lookup function follow the blocked-time rule.

``organizations_with_unannounced_overdue_tasks()`` (migration e5a07b3c9d14)
decides which organizations the overdue scan should look at. It used a plain
"deadline has passed". Since M10 slice E a task is overdue only when it is not
blocked right now and ``due_at`` plus its approved blocked time has passed
(tasks/overdue.py). Without this change the scan would queue a pointless job,
every 10 minutes, for an organization whose only late-looking tasks are
blocked or extended.

Same function name, signature and safety settings (SECURITY DEFINER, pinned
search_path, EXECUTE for elevare_app only); only the WHERE clause changes.

Revision ID: a3d9e61c7b25
Revises: f7b2c91d4a60
Create Date: 2026-10-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3d9e61c7b25'
down_revision: Union[str, Sequence[str], None] = 'f7b2c91d4a60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace the function body with the block-aware rule."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_with_unannounced_overdue_tasks()
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


def downgrade() -> None:
    """Put back the plain 'deadline has passed' version."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_with_unannounced_overdue_tasks()
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
              AND t.due_at < now()
              AND t.overdue_notified_at IS NULL;
        $$
        """
    )
