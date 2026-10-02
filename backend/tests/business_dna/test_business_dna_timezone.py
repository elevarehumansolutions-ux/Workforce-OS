"""HTTP-level tests for the organization timezone set through PUT /business-dna.

The timezone lives on ``organizations`` but is written through the Business
DNA upsert, like ``organization_name`` (08_DECISIONS.md 2026-10-02). It
decides where "midnight" falls for the attendance auto-close.
"""
from unittest.mock import MagicMock

import pytest

from tests.conftest import register_verified_and_login

BUSINESS_DNA = "/api/v1/business-dna"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"
AUDIT = "/api/v1/audit-log"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_a_new_organization_defaults_to_lagos_time(client):
    """Nobody has to set a timezone: it reads Africa/Lagos until they choose one."""
    owner = await register_verified_and_login(client, email="tz_owner1@example.com")
    h = _auth_header(owner["access_token"])

    put = await client.put(BUSINESS_DNA, json={"industry": "Retail"}, headers=h)
    get = await client.get(BUSINESS_DNA, headers=h)

    assert put.status_code == 200
    assert put.json()["timezone"] == "Africa/Lagos"
    assert get.json()["timezone"] == "Africa/Lagos"


@pytest.mark.asyncio
async def test_timezone_can_be_set_and_survives_later_saves_that_omit_it(client):
    """Setting it sticks; the wizard saving other fields afterwards doesn't reset it."""
    owner = await register_verified_and_login(client, email="tz_owner2@example.com")
    h = _auth_header(owner["access_token"])

    first = await client.put(
        BUSINESS_DNA, json={"organization_name": "Acme", "timezone": "Africa/Nairobi"}, headers=h
    )
    later = await client.put(BUSINESS_DNA, json={"vision": "Be the best"}, headers=h)

    assert first.json()["timezone"] == "Africa/Nairobi"
    assert later.json()["timezone"] == "Africa/Nairobi"
    assert (await client.get(BUSINESS_DNA, headers=h)).json()["timezone"] == "Africa/Nairobi"


@pytest.mark.asyncio
async def test_timezone_can_be_set_on_its_own(client):
    """A save that only carries the timezone still creates the profile and sets it."""
    owner = await register_verified_and_login(client, email="tz_owner3@example.com")
    h = _auth_header(owner["access_token"])

    resp = await client.put(BUSINESS_DNA, json={"timezone": "Europe/London"}, headers=h)

    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Europe/London"


@pytest.mark.asyncio
async def test_a_made_up_or_wrongly_cased_timezone_is_rejected(client):
    """Only real IANA names are accepted, spelled exactly; nothing is stored on a rejection."""
    owner = await register_verified_and_login(client, email="tz_owner4@example.com")
    h = _auth_header(owner["access_token"])

    for bad in ["Mars/Olympus", "africa/lagos", "WAT", "", "+01:00"]:
        resp = await client.put(BUSINESS_DNA, json={"timezone": bad}, headers=h)
        assert resp.status_code == 422, bad

    ok = await client.put(BUSINESS_DNA, json={"industry": "Retail"}, headers=h)
    assert ok.json()["timezone"] == "Africa/Lagos"


@pytest.mark.asyncio
async def test_an_explicit_null_timezone_is_ignored_not_an_error(client):
    """The column is NOT NULL: sending null leaves the current value alone instead of failing."""
    owner = await register_verified_and_login(client, email="tz_owner5@example.com")
    h = _auth_header(owner["access_token"])
    await client.put(BUSINESS_DNA, json={"timezone": "Africa/Nairobi"}, headers=h)

    resp = await client.put(BUSINESS_DNA, json={"timezone": None, "industry": "Retail"}, headers=h)

    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Africa/Nairobi"


@pytest.mark.asyncio
async def test_only_hr_admins_can_change_the_timezone_and_orgs_are_independent(client, monkeypatch):
    """A manager gets 403, and changing one org's timezone never touches another's."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    owner = await register_verified_and_login(client, email="tz_owner6@example.com")
    other = await register_verified_and_login(client, email="tz_other6@example.com")
    h = _auth_header(owner["access_token"])
    await client.post(MEMBERSHIPS, json={"email": "tz_mgr6@example.com", "role": "manager"}, headers=h)
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    manager = (
        await client.post(
            f"{AUTH}/accept-invite",
            json={
                "token": token,
                "full_name": "Test Manager",
                "password": "Password123#",
                "confirm_password": "Password123#",
            },
        )
    ).json()

    as_manager = await client.put(
        BUSINESS_DNA, json={"timezone": "Asia/Tokyo"}, headers=_auth_header(manager["access_token"])
    )
    await client.put(BUSINESS_DNA, json={"timezone": "Asia/Tokyo"}, headers=h)
    other_dna = await client.put(
        BUSINESS_DNA, json={"industry": "Retail"}, headers=_auth_header(other["access_token"])
    )

    assert as_manager.status_code == 403
    assert other_dna.json()["timezone"] == "Africa/Lagos"


@pytest.mark.asyncio
async def test_a_timezone_change_is_audit_logged_with_old_and_new(client):
    """The audit trail records the organization-level change, not just business_dna columns."""
    owner = await register_verified_and_login(client, email="tz_owner7@example.com")
    h = _auth_header(owner["access_token"])
    await client.put(BUSINESS_DNA, json={"industry": "Retail"}, headers=h)
    await client.put(BUSINESS_DNA, json={"timezone": "Africa/Nairobi"}, headers=h)

    audit = await client.get(AUDIT, params={"entity_type": "business_dna"}, headers=h)

    changes = [e["changes"] for e in audit.json()["data"] if e["action"] == "update"]
    assert any(
        c["old"].get("organization_timezone") == "Africa/Lagos"
        and c["new"].get("organization_timezone") == "Africa/Nairobi"
        for c in changes
    )
