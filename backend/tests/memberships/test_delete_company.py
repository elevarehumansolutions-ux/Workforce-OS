"""Deleting (archiving) a company (08_DECISIONS.md 2026-11-14).

Scenario: Chidi owns two companies, one made at sign-up and "Zenith Foods". He decides to close
Zenith. He must type its name and his password; nothing is erased, but nobody can enter it any
more and he lands in the first company. He can never delete the only company he has, and only the
owner may.
"""
import pytest
from sqlalchemy import text

from tests.conftest import commit_like_production, register_verified_and_login
from tests.memberships.join_helper import AUTH, DEFAULT_PASSWORD, MEMBERSHIPS, invite_existing, join_existing

CREATE = f"{AUTH}/create-organization"
DELETE = f"{AUTH}/delete-organization"


def _h(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _two_companies(client, email: str):
    """Returns (login for the first company, login for the new company 'Zenith Foods')."""
    first = await register_verified_and_login(client, email=email)
    created = await client.post(CREATE, json={"name": "Zenith Foods"}, headers=_h(first))
    assert created.status_code == 200, created.text
    return first, created.json()


async def _delete(client, login: dict, name: str = "Zenith Foods", password: str = DEFAULT_PASSWORD):
    return await client.post(DELETE, json={"confirm_name": name, "password": password}, headers=_h(login))


@pytest.mark.asyncio
async def test_owner_deletes_a_company_and_lands_in_the_other_one(client, db_session, monkeypatch):
    """The name may be typed in any case. The answer is a session for the first company."""
    first, zenith = await _two_companies(client, "dc_chidi1@example.com")
    commit_like_production(db_session, monkeypatch)

    resp = await _delete(client, zenith, name="  zenith FOODS ")

    assert resp.status_code == 200, resp.text
    assert resp.json()["organization"]["id"] == first["organization"]["id"]
    # The old token for the deleted company no longer works.
    assert (await client.get(MEMBERSHIPS, headers=_h(zenith))).status_code == 401
    # The new one opens the first company, which is untouched.
    assert (await client.get(MEMBERSHIPS, headers=_h(resp.json()))).status_code == 200
    # The deleted company is not listed at all (not even as "access removed").
    me = await client.get(f"{AUTH}/me", headers=_h(resp.json()))
    listed = [m["organization"]["id"] for m in me.json()["memberships"]]
    assert listed == [first["organization"]["id"]]


@pytest.mark.asyncio
async def test_a_wrong_password_deletes_nothing(client):
    first, zenith = await _two_companies(client, "dc_chidi2@example.com")

    resp = await _delete(client, zenith, password="Wrong-password-1")

    assert resp.status_code == 422
    assert "password" in resp.json()["message"].lower()
    assert (await client.get(MEMBERSHIPS, headers=_h(zenith))).status_code == 200


@pytest.mark.asyncio
async def test_a_wrong_name_deletes_nothing(client):
    first, zenith = await _two_companies(client, "dc_chidi3@example.com")

    resp = await _delete(client, zenith, name="Zenith Food")

    assert resp.status_code == 422
    assert (await client.get(MEMBERSHIPS, headers=_h(zenith))).status_code == 200


@pytest.mark.asyncio
async def test_the_only_company_cannot_be_deleted(client):
    """Deleting it would leave Chidi with nowhere to go."""
    only = await register_verified_and_login(client, email="dc_chidi4@example.com")
    renamed = await client.put("/api/v1/business-dna", json={"organization_name": "Solo Ltd"}, headers=_h(only))
    assert renamed.status_code == 200

    resp = await _delete(client, only, name="Solo Ltd")

    assert resp.status_code == 409
    assert resp.json()["code"] == "LAST_COMPANY"
    assert (await client.get(MEMBERSHIPS, headers=_h(only))).status_code == 200


@pytest.mark.asyncio
async def test_only_the_owner_may_delete(client, monkeypatch):
    """An HR administrator who is not the owner is refused."""
    owner, zenith = await _two_companies(client, "dc_owner5@example.com")
    await register_verified_and_login(client, email="dc_hr5@example.com")
    await join_existing(client, monkeypatch, zenith, "dc_hr5@example.com", "hr_administrator")
    hr = await client.post(
        f"{AUTH}/login", json={"email": "dc_hr5@example.com", "password": DEFAULT_PASSWORD}
    )
    switched = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": zenith["organization"]["id"]}, headers=_h(hr.json())
    )
    assert switched.status_code == 200, switched.text

    resp = await _delete(client, switched.json())

    assert resp.status_code == 403
    assert (await client.get(MEMBERSHIPS, headers=_h(zenith))).status_code == 200


@pytest.mark.asyncio
async def test_teammates_lose_access_and_waiting_invites_stop_working(client, monkeypatch):
    first, zenith = await _two_companies(client, "dc_chidi6@example.com")
    mate = await register_verified_and_login(client, email="dc_mate6@example.com")
    await join_existing(client, monkeypatch, zenith, "dc_mate6@example.com", "employee")
    mate_in_zenith = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": zenith["organization"]["id"]}, headers=_h(mate)
    )
    assert mate_in_zenith.status_code == 200
    await register_verified_and_login(client, email="dc_late6@example.com")
    _, waiting_token = await invite_existing(client, monkeypatch, zenith, "dc_late6@example.com", "employee")

    assert (await _delete(client, zenith)).status_code == 200

    assert (await client.get(MEMBERSHIPS, headers=_h(mate_in_zenith.json()))).status_code == 401
    late = await client.post(
        f"{AUTH}/accept-invite-existing", json={"token": waiting_token, "password": DEFAULT_PASSWORD}
    )
    assert late.status_code >= 400


@pytest.mark.asyncio
async def test_a_deleted_company_frees_one_of_the_three_places(client):
    """He owns three; after deleting one he can start another."""
    first = await register_verified_and_login(client, email="dc_chidi7@example.com")
    second = (await client.post(CREATE, json={"name": "Zenith Foods"}, headers=_h(first))).json()
    third = (await client.post(CREATE, json={"name": "Third Ltd"}, headers=_h(second))).json()
    assert (await client.post(CREATE, json={"name": "Fourth Ltd"}, headers=_h(third))).status_code == 409

    assert (await _delete(client, third, name="Third Ltd")).status_code == 200

    again = await client.post(CREATE, json={"name": "Fourth Ltd"}, headers=_h(first))
    assert again.status_code == 200, again.text


@pytest.mark.asyncio
async def test_background_lookups_skip_a_deleted_company(client, db_session):
    first, zenith = await _two_companies(client, "dc_chidi8@example.com")
    sql = text("SELECT organization_id FROM organization_fiscal_months_for_quarterly_review()")
    before = {str(row[0]) for row in (await db_session.execute(sql)).all()}
    assert zenith["organization"]["id"] in before

    assert (await _delete(client, zenith)).status_code == 200

    after = {str(row[0]) for row in (await db_session.execute(sql)).all()}
    assert zenith["organization"]["id"] not in after
    assert first["organization"]["id"] in after
