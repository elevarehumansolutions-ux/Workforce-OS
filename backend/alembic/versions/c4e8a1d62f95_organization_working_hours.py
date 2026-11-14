"""Each company sets its own working week: start hour, end hour and working days.

Workflow deadlines count business hours (workflow/deadlines.py). Until now the week was fixed at Monday
to Friday 09:00 to 17:00. The defaults here are exactly that, so every existing company behaves as before
until it changes them.

Revision ID: c4e8a1d62f95
Revises: b7d31f9e2c60
Create Date: 2026-11-14 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1d62f95'
down_revision: Union[str, Sequence[str], None] = 'b7d31f9e2c60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the three columns and the rules that keep them sensible."""
    op.add_column('organizations', sa.Column('workday_start_hour', sa.SmallInteger(), nullable=False, server_default='9'))
    op.add_column('organizations', sa.Column('workday_end_hour', sa.SmallInteger(), nullable=False, server_default='17'))
    # Weekday numbers, Monday = 0 ... Sunday = 6 (the numbers Python uses).
    op.add_column(
        'organizations',
        sa.Column('work_days', postgresql.ARRAY(sa.SmallInteger()), nullable=False, server_default='{0,1,2,3,4}'),
    )
    op.create_check_constraint('check_workday_start_hour', 'organizations', 'workday_start_hour BETWEEN 0 AND 22')
    op.create_check_constraint('check_workday_end_hour', 'organizations', 'workday_end_hour BETWEEN 1 AND 23')
    op.create_check_constraint(
        'check_workday_start_before_end', 'organizations', 'workday_start_hour < workday_end_hour'
    )
    op.create_check_constraint(
        'check_work_days_valid',
        'organizations',
        'cardinality(work_days) BETWEEN 1 AND 7 AND work_days <@ ARRAY[0,1,2,3,4,5,6]::smallint[]',
    )


def downgrade() -> None:
    """Drop the rules and the columns."""
    op.drop_constraint('check_work_days_valid', 'organizations', type_='check')
    op.drop_constraint('check_workday_start_before_end', 'organizations', type_='check')
    op.drop_constraint('check_workday_end_hour', 'organizations', type_='check')
    op.drop_constraint('check_workday_start_hour', 'organizations', type_='check')
    op.drop_column('organizations', 'work_days')
    op.drop_column('organizations', 'workday_end_hour')
    op.drop_column('organizations', 'workday_start_hour')
