"""A reminder before a task's deadline (08_DECISIONS.md 2026-11-15, "Reminder before the deadline").

``tasks.due_soon_notified_at`` marks a task whose "due soon" reminder has been sent, like ``overdue_notified_at`` does
for the overdue alert (it is cleared in the same places, when the deadline moves). The task scan's cross-tenant lookup
``organizations_needing_task_scan()`` gains a third reason to return an organization: an assigned open task that is
inside its reminder window and not yet reminded. The window is a quarter of the task's life, never less than 1 hour
and never more than 1 day, and a task whose whole life is no longer than that gets no reminder (the same rule as
``tasks/overdue.py`` ``is_due_soon``). Still SECURITY DEFINER with a pinned search_path; organization ids only.

Revision ID: a1d7c3f95e48
Revises: f7b4d9e25a31
Create Date: 2026-11-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1d7c3f95e48'
down_revision: Union[str, Sequence[str], None] = 'f7b4d9e25a31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the marker and widen the lookup."""
    op.add_column('tasks', sa.Column('due_soon_notified_at', sa.DateTime(timezone=True), nullable=True))
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
            CROSS JOIN LATERAL (
                SELECT t.due_at + make_interval(secs => t.approved_blocked_seconds) AS real_due
            ) r
            CROSS JOIN LATERAL (
                SELECT LEAST(GREATEST((r.real_due - t.created_at) * 0.25, interval '1 hour'), interval '1 day') AS lead_time
            ) l
            WHERE t.deleted_at IS NULL
              AND t.organization_id IN (SELECT o.id FROM organizations o WHERE o.archived_at IS NULL)
              AND t.status IN ('open', 'in_progress')
              AND (
                  (
                      t.due_at IS NOT NULL
                      AND t.blocked_since IS NULL
                      AND r.real_due < now()
                      AND t.overdue_notified_at IS NULL
                  )
                  OR t.assigned_to_employee_id IN (
                      SELECT e.id FROM employees e WHERE e.status = 'inactive'
                  )
                  OR (
                      t.due_at IS NOT NULL
                      AND t.blocked_since IS NULL
                      AND t.assigned_to_employee_id IS NOT NULL
                      AND t.due_soon_notified_at IS NULL
                      AND r.real_due > now()
                      AND r.real_due - now() <= l.lead_time
                      AND r.real_due - t.created_at > l.lead_time
                  )
              );
        $$
        """
    )


def downgrade() -> None:
    """Restore the previous lookup (overdue and offboarded reasons only) and drop the marker."""
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
    op.drop_column('tasks', 'due_soon_notified_at')
