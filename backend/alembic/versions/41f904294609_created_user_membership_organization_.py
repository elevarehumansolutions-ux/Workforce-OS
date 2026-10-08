"""Create the User, Membership, and Organization tables.

Revision ID: 41f904294609
Revises:
Create Date: 2026-09-10 17:34:39.074896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41f904294609'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create organizations, users, and memberships tables with tenant-isolation RLS.

    Creates the three founding tables, enables row level security on
    ``organizations`` and ``memberships`` (``users`` is deliberately
    excluded — it has no ``organization_id``), and adds a
    ``tenant_isolation`` policy on each that scopes visibility to
    ``app.current_org_id`` while still allowing the bootstrap insert during
    registration, when no org context has been set yet.
    """
    op.create_table('organizations',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('subscription_status', sa.String(length=50), server_default='trial', nullable=False),
    sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fiscal_year_start_month', sa.Integer(), server_default='1', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('fiscal_year_start_month BETWEEN 1 AND 12', name='check_fiscal_year_start_month'),
    sa.CheckConstraint("subscription_status IN ('trial', 'active', 'expired', 'cancelled')", name='check_subscription_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('auth_provider', sa.String(length=30), server_default='password', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_verified', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('memberships',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=50), server_default='employee', nullable=False),
    sa.Column('is_owner', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(
        "role IN ('hr_administrator', 'manager', 'business_executive', 'employee', 'system_administrator')",
        name='check_membership_role'
    ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'user_id', name='uq_memberships_organization_user')
    )

    # Enable Row Level Security.
    # `users` deliberately has none: it carries no organization_id, since a
    # User is an identity independent of any org (04_DATABASE.md Cluster 1
    # design note) — the tenant boundary starts at `memberships`.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE memberships ENABLE ROW LEVEL SECURITY")

    # Tenant-isolation policies.
    #
    # USING governs SELECT/UPDATE/DELETE visibility: only rows belonging to
    # the session's current org (set via `SET LOCAL app.current_org_id` in
    # the tenant-context dependency) are visible.
    #
    # WITH CHECK governs INSERT (and the post-update row): it additionally
    # allows the write when app.current_org_id has never been set at all.
    # This is what lets registration create the very first `organizations`
    # row and the founding-Owner `memberships` row before any tenant context
    # exists — at that point in the request there IS no org yet, so there is
    # nothing for the policy to compare against, and Postgres would otherwise
    # reject the insert.
    op.execute(
        """
        CREATE POLICY tenant_isolation ON organizations
        USING (id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (
            NULLIF(current_setting('app.current_org_id', true), '') IS NULL
            OR id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON memberships
        USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (
            NULLIF(current_setting('app.current_org_id', true), '') IS NULL
            OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    """Drop the tenant-isolation policies and the organizations/users/memberships tables."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON memberships")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON organizations")
    op.drop_table('memberships')
    op.drop_table('users')
    op.drop_table('organizations')
