"""The reviewer sets the extra time for an approved block (08_DECISIONS.md 2026-11-16, "The reviewer sets the time").

Two optional columns on ``task_blocks``:

* ``estimated_seconds``: what the assignee said they would need when they marked the task blocked. It only pre-fills
  the reviewer's box; the reviewer decides.
* ``granted_seconds``: the extra time the reviewer gave when approving. It is added to the task's running total at
  approval, so what the person does afterwards cannot change it. A block approved under the old rule (time = how long
  it lasted) has no value here and is still credited that way if it is closed later.

Revision ID: b2e8f4a60c37
Revises: a1d7c3f95e48
Create Date: 2026-11-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e8f4a60c37'
down_revision: Union[str, Sequence[str], None] = 'a1d7c3f95e48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the two columns and their rules."""
    op.add_column('task_blocks', sa.Column('estimated_seconds', sa.Integer(), nullable=True))
    op.add_column('task_blocks', sa.Column('granted_seconds', sa.Integer(), nullable=True))
    op.create_check_constraint(
        'check_task_block_estimated_positive', 'task_blocks', 'estimated_seconds IS NULL OR estimated_seconds > 0'
    )
    op.create_check_constraint(
        'check_task_block_granted_positive', 'task_blocks', 'granted_seconds IS NULL OR granted_seconds > 0'
    )
    op.create_check_constraint(
        'check_task_block_granted_only_when_approved',
        'task_blocks',
        "granted_seconds IS NULL OR review_status = 'approved'",
    )


def downgrade() -> None:
    """Drop the rules and the columns (the reviewer's granted time is lost; the task totals keep it)."""
    op.drop_constraint('check_task_block_granted_only_when_approved', 'task_blocks', type_='check')
    op.drop_constraint('check_task_block_granted_positive', 'task_blocks', type_='check')
    op.drop_constraint('check_task_block_estimated_positive', 'task_blocks', type_='check')
    op.drop_column('task_blocks', 'granted_seconds')
    op.drop_column('task_blocks', 'estimated_seconds')
