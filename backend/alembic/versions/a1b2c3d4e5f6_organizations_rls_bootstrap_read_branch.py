"""Add bootstrap-read branch to the organizations RLS policy for GET /me multi-org support.

Revision ID: a1b2c3d4e5f6
Revises: ce685af9fd0d
Create Date: 2026-09-18 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'ce685af9fd0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace organizations' tenant_isolation policy with a bootstrap-read variant.

    Adds a USING-clause branch that, when no org is yet selected
    (``app.current_org_id`` unset), allows a session identified only by
    ``app.current_user_id`` to see every organization row it holds a
    membership in — mirroring the bootstrap pattern memberships' own policy
    already uses. Needed for GET /me multi-org support: without it, RLS
    only ever allowed seeing one org's row at a time.
    """
    # organizations' USING clause had no bootstrap-read exception at all
    # (only WITH CHECK, for registration's insert) — meaning a session
    # identified only by app.current_user_id (login, GET /me, before any one
    # org is chosen) could never see ANY organization row, including ones
    # the user is a genuine member of. This broke GET /me for any
    # multi-membership user: RLS only ever allows seeing one org's row at a
    # time otherwise, so there was no way to fetch every org a user belongs
    # to for the frontend's org-switcher. Fixed by mirroring the exact same
    # bootstrap pattern memberships' own policy already uses, scoped through
    # real membership rows (not "see every organization" — only ones this
    # user_id actually belongs to).
    op.execute("DROP POLICY tenant_isolation ON organizations")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON organizations
        USING (
            id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
            OR (
                NULLIF(current_setting('app.current_org_id', true), '') IS NULL
                AND id IN (
                    SELECT organization_id FROM memberships
                    WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                )
            )
        )
        WITH CHECK (
            NULLIF(current_setting('app.current_org_id', true), '') IS NULL
            OR id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    """Restore organizations' tenant_isolation policy to its single-org-only form."""
    op.execute("DROP POLICY tenant_isolation ON organizations")
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
