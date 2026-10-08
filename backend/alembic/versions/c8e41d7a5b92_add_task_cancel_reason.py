"""Add tasks.cancel_reason.

A cancelled task records why (08_DECISIONS.md 2026-10-07: the reason is required
and shown on the task). The CHECK mirrors ``check_task_completed_at_matches_status``:
the reason is set exactly when the status is ``cancelled``. Every existing row is
open, in progress or completed, so there is nothing to backfill.

Revision ID: c8e41d7a5b92
Revises: 14b29721b95f
Create Date: 2026-10-08 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e41d7a5b92'
down_revision: Union[str, Sequence[str], None] = '14b29721b95f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable column and the CHECK tying it to the status."""
    op.add_column('tasks', sa.Column('cancel_reason', sa.Text(), nullable=True))
    op.create_check_constraint(
        'check_task_cancel_reason_matches_status',
        'tasks',
        "(status = 'cancelled' AND cancel_reason IS NOT NULL)"
        " OR (status <> 'cancelled' AND cancel_reason IS NULL)",
    )


def downgrade() -> None:
    """Drop the CHECK, then the column."""
    op.drop_constraint('check_task_cancel_reason_matches_status', 'tasks', type_='check')
    op.drop_column('tasks', 'cancel_reason')
