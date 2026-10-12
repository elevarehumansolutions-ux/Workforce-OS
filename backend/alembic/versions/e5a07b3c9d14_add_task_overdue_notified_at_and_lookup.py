"""Add tasks.overdue_notified_at and the cross-tenant overdue lookup.

Two things the overdue scan (M10 slice D) needs:

1. ``tasks.overdue_notified_at``: when the "this task is overdue" notification
   was sent. NULL means "not sent yet". The scan only announces tasks where it
   is NULL, then sets it, so each overdue task is announced once. Changing a
   task's deadline or reassigning it sets it back to NULL (done in the Task
   code), so a new deadline gets its own alert. Existing rows start as NULL.

2. ``organizations_with_unannounced_overdue_tasks()``: the scan runs with no
   tenant context, so under row-level security it can't ask "which
   organizations have overdue tasks I haven't announced?". Same solution as
   ``organizations_with_open_attendance()``: a ``SECURITY DEFINER`` SQL
   function that runs as the schema-owning role RLS already exempts.
   ``elevare_app`` is granted ``EXECUTE`` on this one function only, and it
   returns nothing but organization ids: no task, no person, no count.
   Everything after that happens per organization under normal RLS.
   ``SET search_path`` is required on any ``SECURITY DEFINER`` function so a
   caller's session setting can't redirect a name inside it.

Revision ID: e5a07b3c9d14
Revises: c8e41d7a5b92
Create Date: 2026-10-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a07b3c9d14'
down_revision: Union[str, Sequence[str], None] = 'c8e41d7a5b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the marker column and the lookup function."""
    op.add_column('tasks', sa.Column('overdue_notified_at', sa.DateTime(timezone=True), nullable=True))
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
              AND t.due_at < now()
              AND t.overdue_notified_at IS NULL;
        $$
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION organizations_with_unannounced_overdue_tasks() TO elevare_app"
    )


def downgrade() -> None:
    """Drop the lookup function, then the column."""
    op.execute("DROP FUNCTION IF EXISTS organizations_with_unannounced_overdue_tasks()")
    op.drop_column('tasks', 'overdue_notified_at')
