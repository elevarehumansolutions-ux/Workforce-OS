"""HTTP- and database-level tests for email normalization.

Every email is trimmed and lower-cased on input (``NormalizedEmail``), looked
up in that same form, and the database refuses anything else, so
``Chidi@X.com`` and ``chidi@x.com`` are always the same account
(08_DECISIONS.md 2026-10-02).
"""
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import register_payload, register_verified_and_login

AUTH = "/api/v1/auth"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_registration_stores_the_email_lower_cased_and_login_ignores_case(client):
    """Registering 'Mixed.Case@Example.COM ' is stored lower-cased and any casing logs in."""
    owner = await register_verified_and_login(client, email="  Mixed.Case@Example.COM ")

    assert owner["user"]["email"] == "mixed.case@example.com"
    for variant in ["MIXED.CASE@EXAMPLE.COM", "mixed.case@example.com", " Mixed.Case@Example.com "]:
        resp = await client.post(f"{AUTH}/login", json={"email": variant, "password": "Password123#"})
        assert resp.status_code == 200, variant


@pytest.mark.asyncio
async def test_registering_the_same_email_in_another_case_is_a_conflict(client):
    """A case variant of an existing account is a duplicate, not a second account."""
    await register_verified_and_login(client, email="dup.case@example.com")

    resp = await client.post(f"{AUTH}/register", json=register_payload(email="DUP.Case@Example.com"))

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_user_lookup_normalizes_its_input(client, db_session):
    """The repository lookup finds a user whatever casing/whitespace the caller passes."""
    from app.modules.tenancy_identity.repository import UserRepository

    await register_verified_and_login(client, email="lookup.me@example.com")

    found = await UserRepository(db_session).get_user_by_email("  LOOKUP.ME@Example.com ")

    assert found is not None
    assert found.email == "lookup.me@example.com"


@pytest.mark.asyncio
async def test_invites_are_stored_lower_cased_and_a_case_variant_replaces_the_pending_one(client, monkeypatch):
    """Inviting 'Teammate@X.com' then 'teammate@x.com' leaves one live invite, for the lower-cased address."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    owner = await register_verified_and_login(client, email="norm_owner@example.com")
    h = _auth_header(owner["access_token"])

    await client.post(MEMBERSHIPS, json={"email": "Teammate@Example.com", "role": "employee"}, headers=h)
    await client.post(MEMBERSHIPS, json={"email": "teammate@example.com", "role": "employee"}, headers=h)

    assert [c.args[0] for c in mock_dispatch.delay.call_args_list] == ["teammate@example.com"] * 2
    first = mock_dispatch.delay.call_args_list[0].args[1].split("token=")[1]
    second = mock_dispatch.delay.call_args_list[1].args[1].split("token=")[1]
    body = {"full_name": "Team Mate", "password": "Password123#", "confirm_password": "Password123#"}
    assert (await client.post(f"{AUTH}/accept-invite", json={"token": first, **body})).status_code == 400
    accepted = await client.post(f"{AUTH}/accept-invite", json={"token": second, **body})
    assert accepted.status_code == 200
    assert accepted.json()["user"]["email"] == "teammate@example.com"


@pytest.mark.asyncio
async def test_employee_work_email_is_normalized_and_must_be_an_email(client):
    """work_email is lower-cased on create and update, and a non-email is rejected."""
    owner = await register_verified_and_login(client, email="norm_owner2@example.com")
    h = _auth_header(owner["access_token"])
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        "/api/v1/positions", json={"department_id": dept.json()["id"], "title": "Engineer"}, headers=h
    )
    body = {
        "position_id": pos.json()["id"],
        "first_name": "Chidi",
        "last_name": "Obi",
        "work_email": "  Chidi.Obi@Example.COM ",
        "start_date": date.today().isoformat(),
    }

    created = await client.post(EMPLOYEES, json=body, headers=h)
    updated = await client.patch(
        f"{EMPLOYEES}/{created.json()['id']}", json={"work_email": "CHIDI.OBI2@Example.com"}, headers=h
    )
    invalid = await client.post(EMPLOYEES, json={**body, "work_email": "not-an-email"}, headers=h)

    assert created.status_code == 200
    assert created.json()["work_email"] == "chidi.obi@example.com"
    assert updated.json()["work_email"] == "chidi.obi2@example.com"
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_the_database_refuses_a_non_normalized_email(db_session):
    """Even a write that bypasses the API schemas can't store 'Mixed@X.com'."""
    with pytest.raises(IntegrityError) as exc:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO users (id, email, full_name, password_hash, account_status) "
                    "VALUES (gen_random_uuid(), 'Mixed@X.com', 'Bad Case', 'x', 'verified')"
                )
            )

    assert "check_user_email_normalized" in str(exc.value)
