"""add cross-tenant fiscal month lookup function for quarterly review

Revision ID: c56f442c2848
Revises: 61454952170a
Create Date: 2026-09-27 21:19:07.989212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c56f442c2848'
down_revision: Union[str, Sequence[str], None] = '61454952170a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a narrow, privileged escape hatch for the Quarterly Objective Review Beat job.

    The live app's own role (``elevare_app``) never has ``BYPASSRLS``
    (07_SECURITY.md, settled 2026-09-17) — genuinely enforced, not just a
    policy on paper. But the Beat job structurally needs one cross-tenant
    read: which orgs' fiscal quarter just turned over. With no tenant
    context set at all, ``organizations``' RLS policy returns zero rows,
    so there is no way to ask that question as ``elevare_app`` today.

    This function is created by (and so owned by) the schema-owning
    superuser migrations already run as — the same role ``organizations``
    itself is owned by, which RLS already exempts, since ``FORCE ROW LEVEL
    SECURITY`` was never set on it. ``SECURITY DEFINER`` makes the
    function's own query run as its *owner*, not its caller, so granting
    ``elevare_app`` only ``EXECUTE`` on this one function hands it exactly
    one piece of cross-tenant data — a bare (id, fiscal_year_start_month)
    list, nothing else about any organization — without ``elevare_app``
    itself gaining any broader privilege. ``elevare_app``'s own role is
    untouched by this migration; every other query it runs is exactly as
    RLS-restricted as before.

    ``SET search_path`` is required on any ``SECURITY DEFINER`` function —
    without pinning it, a malicious ``search_path`` set by the calling
    session could redirect an unqualified name inside the function to a
    same-named object the caller controls (the standard Postgres
    search-path-hijack risk for definer functions).
    """
    op.execute(
        """
        CREATE FUNCTION organization_fiscal_months_for_quarterly_review()
        RETURNS TABLE(organization_id UUID, fiscal_year_start_month INTEGER)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT id, fiscal_year_start_month FROM organizations;
        $$
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION organization_fiscal_months_for_quarterly_review() "
        "TO elevare_app"
    )


def downgrade() -> None:
    """Drop the Quarterly Objective Review's cross-tenant lookup function."""
    op.execute("DROP FUNCTION IF EXISTS organization_fiscal_months_for_quarterly_review()")
