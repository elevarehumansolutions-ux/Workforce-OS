"""Steps and tasks that several departments do together.

Three pieces (08_DECISIONS.md 2026-11-14, "Together steps"):

* ``workflow_step_participants``: the EXTRA departments (each with an optional person and KPI) that do a step
  together with the step's own department. Tenant table, so it gets the row-level-security policy.
* ``workflow_steps.completion_rule``: ``all`` (the case moves on when every task of the step has ended) or
  ``lead`` (only the step's own department's task counts; the others are helpers).
* ``tasks.workflow_task_role`` (``lead`` or ``participant``; empty for an ordinary one-department step) and
  ``tasks.shared_group_id`` (links the sibling tasks of a one-off task assigned to several departments at once).

Revision ID: f7b4d9e25a31
Revises: e6a3c8f14d27
Create Date: 2026-11-14 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b4d9e25a31'
down_revision: Union[str, Sequence[str], None] = 'e6a3c8f14d27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the rule, the participants table and the two task columns."""
    op.add_column(
        'workflow_steps',
        sa.Column('completion_rule', sa.String(length=10), server_default='all', nullable=False),
    )
    op.create_check_constraint(
        'check_workflow_step_completion_rule', 'workflow_steps', "completion_rule IN ('all', 'lead')"
    )

    op.create_table(
        'workflow_step_participants',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('workflow_step_id', sa.UUID(), nullable=False),
        sa.Column('department_id', sa.UUID(), nullable=False),
        sa.Column('default_assignee_employee_id', sa.UUID(), nullable=True),
        sa.Column('kpi_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['workflow_step_id'], ['workflow_steps.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['default_assignee_employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['kpi_id'], ['kpis.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_workflow_step_participants_organization_id', 'workflow_step_participants', ['organization_id'])
    op.create_index('ix_workflow_step_participants_workflow_step_id', 'workflow_step_participants', ['workflow_step_id'])
    # Autogenerate never writes RLS, so the new table gets its policy here (same as the other workflow tables).
    op.execute("ALTER TABLE workflow_step_participants ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON workflow_step_participants
        USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """
    )

    op.add_column('tasks', sa.Column('workflow_task_role', sa.String(length=12), nullable=True))
    op.create_check_constraint(
        'check_task_workflow_task_role',
        'tasks',
        "workflow_task_role IS NULL OR workflow_task_role IN ('lead', 'participant')",
    )
    op.add_column('tasks', sa.Column('shared_group_id', sa.UUID(), nullable=True))
    op.create_index('ix_tasks_shared_group_id', 'tasks', ['shared_group_id'])


def downgrade() -> None:
    """Drop everything added above (steps lose their extra departments; tasks lose their links)."""
    op.drop_index('ix_tasks_shared_group_id', table_name='tasks')
    op.drop_column('tasks', 'shared_group_id')
    op.drop_constraint('check_task_workflow_task_role', 'tasks', type_='check')
    op.drop_column('tasks', 'workflow_task_role')

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workflow_step_participants")
    op.drop_index('ix_workflow_step_participants_workflow_step_id', table_name='workflow_step_participants')
    op.drop_index('ix_workflow_step_participants_organization_id', table_name='workflow_step_participants')
    op.drop_table('workflow_step_participants')

    op.drop_constraint('check_workflow_step_completion_rule', 'workflow_steps', type_='check')
    op.drop_column('workflow_steps', 'completion_rule')
