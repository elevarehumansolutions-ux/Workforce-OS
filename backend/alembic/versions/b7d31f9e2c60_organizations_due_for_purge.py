"""A narrow lookup for the nightly purge: which deleted companies are old enough to erase for good.

Same shape and reasoning as ``organizations_needing_scoring()``: the app role never has BYPASSRLS, and
the purge job has no single company to start from, so it asks this ``SECURITY DEFINER`` function which
company ids are due. It reveals ids only, and only for companies archived more than ``retention_days`` ago.

Revision ID: b7d31f9e2c60
Revises: a9c52e7d1b48
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7d31f9e2c60'
down_revision: Union[str, Sequence[str], None] = 'a9c52e7d1b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the lookup and let only the application role run it."""
    op.execute(
        """
        CREATE FUNCTION organizations_due_for_purge(retention_days INTEGER)
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT o.id
            FROM organizations o
            WHERE o.archived_at IS NOT NULL
              AND o.archived_at < now() - make_interval(days => retention_days);
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION organizations_due_for_purge(INTEGER) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION organizations_due_for_purge(INTEGER) TO elevare_app")


def downgrade() -> None:
    """Remove the lookup."""
    op.execute("DROP FUNCTION IF EXISTS organizations_due_for_purge(INTEGER)")
