"""A workflow step can name the KPI its tasks count toward.

Until now every task a workflow created had no KPI, so workflow work never counted in anyone's score
(scoring only counts tasks linked to a KPI of the person's department). ``kpi_id`` is optional; the
task a step creates carries it.

Revision ID: e6a3c8f14d27
Revises: d5f2b7a93c18
Create Date: 2026-11-14 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e6a3c8f14d27'
down_revision: Union[str, Sequence[str], None] = 'd5f2b7a93c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the optional KPI column."""
    op.add_column('workflow_steps', sa.Column('kpi_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_workflow_steps_kpi_id_kpis', 'workflow_steps', 'kpis', ['kpi_id'], ['id'])
    op.create_index('ix_workflow_steps_kpi_id', 'workflow_steps', ['kpi_id'])


def downgrade() -> None:
    """Drop the column (steps lose their KPI link; tasks already created keep theirs)."""
    op.drop_index('ix_workflow_steps_kpi_id', table_name='workflow_steps')
    op.drop_constraint('fk_workflow_steps_kpi_id_kpis', 'workflow_steps', type_='foreignkey')
    op.drop_column('workflow_steps', 'kpi_id')
