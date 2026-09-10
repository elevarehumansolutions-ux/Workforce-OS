"""
Schema-level RLS checks. These don't test behavior, they test that RLS is even
turned on, by asking Postgres's own system catalogs about itself.
"""
import pytest
from sqlalchemy import create_engine, text

# Tables that intentionally carry no organization_id — see 04_DATABASE.md Conventions.
TABLES_WITHOUT_RLS = {"organizations", "users"}


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine("postgresql+psycopg://test_user:test_pass@localhost:5432/elevare_test")
    yield engine
    engine.dispose()


def test_every_tenant_table_has_rls_enabled(db_engine):
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
    """rowsecurity=true with zero policies is a different bug than the one we
    actually care about: it blocks ALL access on that table, not scoped access.
    Still worth catching on its own, it means someone enabled RLS and forgot
    the policy that makes it useful."""
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
