"""
Behavioral RLS check: proves a session scoped to one organization actually
cannot see another organization's rows, not just that a policy exists.
"""
import uuid
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture(scope="function")
def db_connection():
    """Fresh connection + transaction per test, rolled back at the end so no
    test leaves data behind for the next one."""
    engine = create_engine("postgresql+psycopg://test_user:test_pass@localhost:5432/elevare_test")
    conn = engine.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()
    engine.dispose()


@pytest.fixture
def two_organizations(db_connection):
    """Seeds two real tenants so there's something real to prove isolation between."""
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())

    db_connection.execute(
        text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
        [{"id": org_a_id, "name": "Org A"}, {"id": org_b_id, "name": "Org B"}],
    )
    db_connection.execute(
        text("INSERT INTO departments (id, organization_id, name) VALUES (:id, :org_id, :name)"),
        [{"id": str(uuid.uuid4()), "org_id": org_b_id, "name": "Org B's Secret Department"}],
    )

    return {"org_a_id": org_a_id, "org_b_id": org_b_id}


def test_org_a_cannot_see_org_bs_departments(db_connection, two_organizations):
    db_connection.execute(
        text("SET LOCAL app.current_org_id = :org_id"),
        {"org_id": two_organizations["org_a_id"]},
    )

    result = db_connection.execute(text("SELECT * FROM departments")).fetchall()

    assert result == [], "Org A's session was able to see a row belonging to Org B"
