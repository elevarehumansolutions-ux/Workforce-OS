"""Add the lookup that tells the nightly scoring job which organizations to work on.

The scoring job (M12, every night) must start from a list of organizations, but
a job has no tenant context yet, so row-level security would show it nothing.
This function is the one narrow way past that, built exactly like the overdue
scan's ``organizations_needing_task_scan()``: SECURITY DEFINER, pinned
search_path, EXECUTE granted to elevare_app only, organization ids and nothing
else.

An organization is returned when it has at least one KPI, or at least one task
with a deadline: those are the organizations that can have a score. It is the
Scoring module's one cross-tenant function (logged in 07_SECURITY.md).

Revision ID: fc24c1890470
Revises: c84e1d5d299f
Create Date: 2026-10-22 10:05:12.598334

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fc24c1890470'
down_revision: Union[str, Sequence[str], None] = 'c84e1d5d299f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the lookup function and let the application role run it."""
    op.execute(
        """
        CREATE FUNCTION organizations_needing_scoring()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT o.id
            FROM organizations o
            WHERE EXISTS (
                SELECT 1 FROM kpis k
                WHERE k.organization_id = o.id AND k.deleted_at IS NULL
            )
            OR EXISTS (
                SELECT 1 FROM tasks t
                WHERE t.organization_id = o.id
                  AND t.deleted_at IS NULL
                  AND t.due_at IS NOT NULL
            );
        $$
        """
    )
    # Postgres lets every role (PUBLIC) run a new function by default. Take that away,
    # so that only the application role can call this one.
    op.execute("REVOKE EXECUTE ON FUNCTION organizations_needing_scoring() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION organizations_needing_scoring() TO elevare_app")


def downgrade() -> None:
    """Drop the lookup function."""
    op.execute("DROP FUNCTION IF EXISTS organizations_needing_scoring()")
