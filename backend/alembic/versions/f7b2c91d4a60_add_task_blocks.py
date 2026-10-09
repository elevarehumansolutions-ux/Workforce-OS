"""Add task_blocks and the two blocked-time facts on tasks.

M10 slice E (08_DECISIONS.md 2026-10-09):

- ``tasks.blocked_since``: when the current block started; NULL = not blocked now.
- ``tasks.approved_blocked_seconds``: running total of reviewer-approved blocked
  time, added to ``due_at`` when judging "overdue". Existing tasks start at 0.
- ``task_blocks``: one row per blocked period of a task, with the reviewer's
  decision. At most one open block (``unblocked_at`` empty) per task, enforced by
  a partial unique index. Row-level security like every tenant table.

Revision ID: f7b2c91d4a60
Revises: e5a07b3c9d14
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2c91d4a60'
down_revision: Union[str, Sequence[str], None] = 'e5a07b3c9d14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the two facts to tasks, create task_blocks, and enable row-level security."""
    op.add_column('tasks', sa.Column('blocked_since', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'tasks',
        sa.Column('approved_blocked_seconds', sa.Integer(), server_default='0', nullable=False),
    )
    op.create_check_constraint(
        'check_task_approved_blocked_seconds_not_negative',
        'tasks',
        'approved_blocked_seconds >= 0',
    )

    op.create_table(
        'task_blocks',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('task_id', sa.UUID(), nullable=False),
        sa.Column('blocked_by_user_id', sa.UUID(), nullable=False),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('blocked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('unblocked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('reviewed_by_user_id', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "category IN ('awaiting_approval', 'awaiting_other_department', 'external_dependency', 'other')",
            name='check_task_block_category',
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name='check_task_block_review_status',
        ),
        sa.CheckConstraint(
            'unblocked_at IS NULL OR unblocked_at >= blocked_at',
            name='check_task_block_unblocked_after_blocked',
        ),
        sa.CheckConstraint(
            "(review_status = 'pending' AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL)"
            " OR (review_status <> 'pending' AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name='check_task_block_review_fields_match_status',
        ),
        sa.ForeignKeyConstraint(['blocked_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_task_blocks_org_review', 'task_blocks', ['organization_id', 'review_status'], unique=False)
    op.create_index(op.f('ix_task_blocks_organization_id'), 'task_blocks', ['organization_id'], unique=False)
    op.create_index(op.f('ix_task_blocks_task_id'), 'task_blocks', ['task_id'], unique=False)
    op.create_index(
        'uq_task_blocks_one_open_per_task',
        'task_blocks',
        ['task_id'],
        unique=True,
        postgresql_where=sa.text('unblocked_at IS NULL'),
    )

    op.execute("ALTER TABLE task_blocks ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON task_blocks
        USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    """Drop the policy and table, then the two columns on tasks."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON task_blocks")
    op.drop_index('uq_task_blocks_one_open_per_task', table_name='task_blocks', postgresql_where=sa.text('unblocked_at IS NULL'))
    op.drop_index(op.f('ix_task_blocks_task_id'), table_name='task_blocks')
    op.drop_index(op.f('ix_task_blocks_organization_id'), table_name='task_blocks')
    op.drop_index('idx_task_blocks_org_review', table_name='task_blocks')
    op.drop_table('task_blocks')
    op.drop_constraint('check_task_approved_blocked_seconds_not_negative', 'tasks', type_='check')
    op.drop_column('tasks', 'approved_blocked_seconds')
    op.drop_column('tasks', 'blocked_since')
