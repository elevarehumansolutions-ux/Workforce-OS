"""Add cross-tenant lookup of organizations that have open attendance records.

Revision ID: 774346b5b100
Revises: 83927f74b4eb
Create Date: 2026-10-02 15:55:17.513514

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '774346b5b100'
down_revision: Union[str, Sequence[str], None] = '83927f74b4eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a narrow, privileged escape hatch for the nightly attendance auto-close job.

    Same shape and same reasoning as
    ``organization_fiscal_months_for_quarterly_review()`` (migration
    ``c56f442c2848``). The live app role (``elevare_app``) never has
    ``BYPASSRLS``, yet the auto-close Beat job has no single tenant to start
    from: it must discover *which* organizations have anyone still clocked
    in. With no tenant context set, RLS returns zero rows, so that question
    cannot be asked as ``elevare_app`` directly.

    ``SECURITY DEFINER`` runs the function's query as its owner, the
    schema-owning role RLS already exempts. ``elevare_app`` is granted
    ``EXECUTE`` on this one function only, so it learns exactly one thing
    across tenants: the id and timezone of each organization that currently
    has at least one open attendance record. No employee, no time, no
    count. Everything after that (the actual closing) happens per
    organization under normal RLS.

    ``SET search_path`` is required on any ``SECURITY DEFINER`` function so a
    caller's session setting can't redirect an unqualified name inside it.
    """
    op.execute(
        """
        CREATE FUNCTION organizations_with_open_attendance()
        RETURNS TABLE(organization_id UUID, timezone VARCHAR)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.timezone
            FROM organizations o
            WHERE EXISTS (
                SELECT 1 FROM attendance_records a
                WHERE a.organization_id = o.id AND a.clock_out_at IS NULL
            );
        $$
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION organizations_with_open_attendance() TO elevare_app")


def downgrade() -> None:
    """Drop the attendance auto-close job's cross-tenant lookup function."""
    op.execute("DROP FUNCTION IF EXISTS organizations_with_open_attendance()")
