"""A workflow step's turnaround can be given in working days instead of hours.

``default_turnaround_hours`` stays as it is. ``default_turnaround_days`` is the alternative: only one of the
two may be set. A day is a full working day of the company's own hours, worked out when the task is created
(workflow/deadlines.py), so "2 days" stays right if the company later changes its working hours.

Revision ID: d5f2b7a93c18
Revises: c4e8a1d62f95
Create Date: 2026-11-14 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5f2b7a93c18'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1d62f95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the days column and the two rules."""
    op.add_column('workflow_steps', sa.Column('default_turnaround_days', sa.Integer(), nullable=True))
    op.create_check_constraint(
        'check_workflow_step_turnaround_days_positive',
        'workflow_steps',
        'default_turnaround_days IS NULL OR default_turnaround_days > 0',
    )
    op.create_check_constraint(
        'check_workflow_step_turnaround_one_unit',
        'workflow_steps',
        'default_turnaround_hours IS NULL OR default_turnaround_days IS NULL',
    )


def downgrade() -> None:
    """Drop the rules and the column (a step given in days loses its deadline)."""
    op.drop_constraint('check_workflow_step_turnaround_one_unit', 'workflow_steps', type_='check')
    op.drop_constraint('check_workflow_step_turnaround_days_positive', 'workflow_steps', type_='check')
    op.drop_column('workflow_steps', 'default_turnaround_days')
