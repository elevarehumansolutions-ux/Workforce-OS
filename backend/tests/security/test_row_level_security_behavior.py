"""Behavioral RLS check: proves a session scoped to one organization actually cannot see another organization's rows, not just that a policy exists.

Exercises organizations/memberships specifically, since those are the two
tables with real policies today (see docs/RLS_POLICIES_EXPLAINED.md). This
gets extended with more tables as later milestones land, not rewritten from
scratch — the pattern (seed two orgs, set context, assert the other org's
rows are invisible) is the same regardless of which table is under test.
"""
import uuid
import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings


@pytest.fixture(scope="function")
def db_connection():
    """Fresh connection + transaction per test, rolled back at the end so no test leaves data behind for the next one."""
    engine = create_engine(settings.database_url)
    conn = engine.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()
    engine.dispose()


@pytest.fixture
def two_organizations_with_members(db_connection):
    """Seeds two real tenants, each with one user and one membership, so there's something real to prove isolation between on both tables."""
    org_a_id, org_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    user_a_id, user_b_id = str(uuid.uuid4()), str(uuid.uuid4())

    # Bootstrap branch (WITH CHECK's "no org context yet" exception, see
    # RLS_POLICIES_EXPLAINED.md §4) is what allows these inserts to run
    # at all — no app.current_org_id is set yet at this point.
    db_connection.execute(
        text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
        [{"id": org_a_id, "name": "Org A"}, {"id": org_b_id, "name": "Org B"}],
    )
    db_connection.execute(
        text(
            "INSERT INTO users (id, email, full_name, password_hash, account_status) "
            "VALUES (:id, :email, 'Test User', 'x', 'verified')"
        ),
        [
            {"id": user_a_id, "email": f"a-{user_a_id}@example.com"},
            {"id": user_b_id, "email": f"b-{user_b_id}@example.com"},
        ],
    )
    db_connection.execute(
        text(
            "INSERT INTO memberships (id, organization_id, user_id, role, is_owner) "
            "VALUES (:id, :org_id, :user_id, 'hr_administrator', true)"
        ),
        [
            {"id": str(uuid.uuid4()), "org_id": org_a_id, "user_id": user_a_id},
            {"id": str(uuid.uuid4()), "org_id": org_b_id, "user_id": user_b_id},
        ],
    )

    return {"org_a_id": org_a_id, "org_b_id": org_b_id, "user_a_id": user_a_id, "user_b_id": user_b_id}


def test_org_a_cannot_see_org_b(db_connection, two_organizations_with_members):
    """With app.current_org_id set to Org A, queries against organizations and memberships return no Org B rows."""
    # SET LOCAL doesn't accept bind parameters (Postgres requires a literal
    # there) — set_config() is a real function call and does, which is
    # exactly why the app itself uses set_config(), never SET LOCAL directly
    # (see auth/service.py). Matching that here, not inventing a second way.
    db_connection.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": two_organizations_with_members["org_a_id"]},
    )

    orgs = db_connection.execute(text("SELECT * FROM organizations")).fetchall()
    memberships = db_connection.execute(text("SELECT * FROM memberships")).fetchall()

    org_ids_seen = {str(row.id) for row in orgs}
    membership_org_ids_seen = {str(row.organization_id) for row in memberships}

    assert two_organizations_with_members["org_b_id"] not in org_ids_seen, \
        "Org A's session was able to see Org B's organization row"
    assert two_organizations_with_members["org_b_id"] not in membership_org_ids_seen, \
        "Org A's session was able to see a membership row belonging to Org B"


def test_no_org_context_sees_only_your_own_membership_by_user_id(
    db_connection, two_organizations_with_members
):
    """With no org context, a session identified only by app.current_user_id sees only its own membership rows.

    The memberships policy's second bootstrap branch
    (RLS_POLICIES_EXPLAINED.md §5): with no org context at all — login's
    exact situation, before it knows which org to act as — a session
    identified only by app.current_user_id sees its own membership rows,
    and no one else's.
    """
    db_connection.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": two_organizations_with_members["user_a_id"]},
    )

    memberships = db_connection.execute(text("SELECT * FROM memberships")).fetchall()
    user_ids_seen = {str(row.user_id) for row in memberships}

    assert user_ids_seen == {two_organizations_with_members["user_a_id"]}, \
        "A no-org-context session saw a membership row belonging to a different user"
