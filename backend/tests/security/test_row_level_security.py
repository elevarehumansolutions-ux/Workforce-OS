"""Schema-level RLS checks. These don't test behavior, they test that RLS is even turned on, by asking Postgres's own system catalogs about itself."""
import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings

# Tables deliberately exempt from RLS, and why:
#   - alembic_version: Alembic's own migration bookkeeping, not tenant data.
#   - users: global identity, no organization_id — see 04_DATABASE.md Conventions.
#   - refresh_tokens / email_verification_tokens / password_reset_tokens / invites:
#     looked up by a raw bearer token before any tenant context can possibly
#     exist yet, RLS scoped to app.current_org_id would block the one
#     operation each of these exists to support (see auth/models.py,
#     tenancy_identity/models.py Invite docstring).
# organizations and memberships are NOT here — both have real RLS policies
# (docs/RLS_POLICIES_EXPLAINED.md) and must be checked like everything else.
TABLES_WITHOUT_RLS = {
    "alembic_version",
    "users",
    "refresh_tokens",
    "email_verification_tokens",
    "password_reset_tokens",
    "invites",
}


@pytest.fixture(scope="module")
def db_engine():
    """Provide a sync SQLAlchemy engine against the test database for raw catalog queries."""
    # settings.database_url uses postgresql+psycopg (psycopg3), which works
    # for both sync (create_engine, here) and async (create_async_engine,
    # conftest.py) engines under the same URL — no driver swap needed, just
    # reuse the real config instead of a separate hardcoded connection string.
    engine = create_engine(settings.database_url)
    yield engine
    engine.dispose()


def test_every_tenant_table_has_rls_enabled(db_engine):
    """Every table in the public schema, except the documented exemptions, has rowsecurity enabled."""
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tablename, rowsecurity
            FROM pg_tables
            WHERE schemaname = 'public'
        """)).fetchall()

    assert rows, "No tables found — is the test database migrated?"

    for tablename, rowsecurity in rows:
        if tablename in TABLES_WITHOUT_RLS:
            continue
        assert rowsecurity, f"{tablename} does not have Row-Level Security enabled"


def test_every_rls_table_has_at_least_one_policy(db_engine):
    """Every table with RLS enabled (outside the documented exemptions) has at least one policy defined.

    rowsecurity=true with zero policies is a different bug than the one we
    actually care about: it blocks ALL access on that table, not scoped
    access. Still worth catching on its own, it means someone enabled RLS
    and forgot the policy that makes it useful.
    """
    with db_engine.connect() as conn:
        tables_with_policies = {
            row[0] for row in conn.execute(text("SELECT DISTINCT tablename FROM pg_policies")).fetchall()
        }
        all_tables = {
            row[0] for row in conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )).fetchall()
        }

    for tablename in all_tables - TABLES_WITHOUT_RLS:
        assert tablename in tables_with_policies, f"{tablename} has RLS enabled but no policy defined"
