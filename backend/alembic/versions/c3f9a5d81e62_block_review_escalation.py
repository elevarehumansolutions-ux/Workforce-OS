"""A block waiting for review too long is escalated (08_DECISIONS.md 2026-11-16, "The reviewer sets the time").

While a block waits for review the task is not counted as overdue, so a reviewer who never decides would freeze the
clock. Two markers on ``task_blocks`` record that the reviewers were reminded (after 24 hours) and that HR was told
(after 48 hours), each once. The task scan's cross-tenant lookup ``organizations_needing_task_scan()`` gains a fourth
reason to return an organization: a pending block past either threshold that has not been announced for it yet.
Still SECURITY DEFINER with a pinned search_path; organization ids only.

Revision ID: c3f9a5d81e62
Revises: b2e8f4a60c37
Create Date: 2026-11-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f9a5d81e62'
down_revision: Union[str, Sequence[str], None] = 'b2e8f4a60c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TASK_REASONS = """
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
              )
"""


def upgrade() -> None:
    """Add the two markers and widen the lookup."""
    op.add_column('task_blocks', sa.Column('review_reminded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('task_blocks', sa.Column('review_escalated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION organizations_needing_task_scan()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            ({_TASK_REASONS})
            UNION
            (
                SELECT b.organization_id
                FROM task_blocks b
                WHERE b.review_status = 'pending'
                  AND b.organization_id IN (SELECT o.id FROM organizations o WHERE o.archived_at IS NULL)
                  AND (
                      (b.review_reminded_at IS NULL AND b.blocked_at < now() - interval '24 hours')
                      OR (b.review_escalated_at IS NULL AND b.blocked_at < now() - interval '48 hours')
                  )
            );
        $$
        """
    )


def downgrade() -> None:
    """Restore the previous lookup (tasks only) and drop the markers."""
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION organizations_needing_task_scan()
        RETURNS TABLE(organization_id UUID)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            {_TASK_REASONS};
        $$
        """
    )
    op.drop_column('task_blocks', 'review_escalated_at')
    op.drop_column('task_blocks', 'review_reminded_at')
