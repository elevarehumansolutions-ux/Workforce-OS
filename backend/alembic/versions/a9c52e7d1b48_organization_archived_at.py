"""Let an owner delete (archive) a company: organizations.archived_at, and skip archived companies in the cross-company lookups.

An archived company keeps all its data, but nobody can enter it and the background jobs ignore it.
The four SECURITY DEFINER lookups the Celery jobs use to find "which companies have work to do"
are re-created with an extra ``archived_at IS NULL`` condition. ``CREATE OR REPLACE`` keeps their
existing grants.

Revision ID: a9c52e7d1b48
Revises: f3b81d6a4e57
Create Date: 2026-11-14 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9c52e7d1b48'
down_revision: Union[str, Sequence[str], None] = 'f3b81d6a4e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the column and re-create the four lookups so they skip archived companies."""
    op.add_column('organizations', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_needing_task_scan()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT DISTINCT t.organization_id
            FROM tasks t
            WHERE t.deleted_at IS NULL
              AND t.organization_id IN (SELECT o.id FROM organizations o WHERE o.archived_at IS NULL)
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
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_with_open_attendance()
        RETURNS TABLE(organization_id UUID, timezone VARCHAR)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.timezone
            FROM organizations o
            WHERE o.archived_at IS NULL
              AND EXISTS (
                SELECT 1 FROM attendance_records a
                WHERE a.organization_id = o.id AND a.clock_out_at IS NULL
            );
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_needing_scoring()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT o.id
            FROM organizations o
            WHERE o.archived_at IS NULL
              AND (
                EXISTS (
                    SELECT 1 FROM kpis k
                    WHERE k.organization_id = o.id AND k.deleted_at IS NULL
                )
                OR EXISTS (
                    SELECT 1 FROM tasks t
                    WHERE t.organization_id = o.id
                      AND t.deleted_at IS NULL
                      AND t.due_at IS NOT NULL
                )
              );
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organization_fiscal_months_for_quarterly_review()
        RETURNS TABLE(organization_id UUID, fiscal_year_start_month INTEGER)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT id, fiscal_year_start_month FROM organizations WHERE archived_at IS NULL;
        $$
        """
    )


def downgrade() -> None:
    """Put the four lookups back as they were, then drop the column."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_needing_task_scan()
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
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_with_open_attendance()
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
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organizations_needing_scoring()
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
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organization_fiscal_months_for_quarterly_review()
        RETURNS TABLE(organization_id UUID, fiscal_year_start_month INTEGER)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT id, fiscal_year_start_month FROM organizations;
        $$
        """
    )
    op.drop_column('organizations', 'archived_at')
