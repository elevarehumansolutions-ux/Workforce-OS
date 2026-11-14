"""Deleting any of your companies from the list, and bringing a deleted one back (08_DECISIONS.md 2026-11-14).

Scenario: Chidi owns a home company and "Zenith Foods". From his list of companies he deletes Zenith
without going into it, later sees it under "deleted companies" and restores it. Teammates who lost
access with the deletion get it back; people an HR administrator had removed earlier do not.
"""
import pytest

from tests.conftest import commit_like_production, register_verified_and_login
from tests.memberships.join_helper import AUTH, DEFAULT_PASSWORD, MEMBERSHIPS, join_existing

CREATE = f"{AUTH}/create-organization"
DELETE = f"{AUTH}/delete-organization"
DELETED = f"{AUTH}/deleted-organizations"
RESTORE = f"{AUTH}/restore-organization"


def _h(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _two_companies(client, email: str):
    """Returns (login for the first company, login for the new company 'Zenith Foods')."""
    first = await register_verified_and_login(client, email=email)
    created = await client.post(CREATE, json={"name": "Zenith Foods"}, headers=_h(first))
    assert created.status_code == 200, created.text
    return first, created.json()


async def _delete_by_id(client, login: dict, org_id: str, name: str = "Zenith Foods"):
    body = {"organization_id": org_id, "confirm_name": name, "password": DEFAULT_PASSWORD}
    return await client.post(DELETE, json=body, headers=_h(login))


async def _in_company(client, user_login: dict, org_id: str) -> dict:
    """A session for one company of a person who belongs to several."""
    switched = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": org_id}, headers=_h(user_login)
    )
    assert switched.status_code == 200, switched.text
    return switched.json()


@pytest.mark.asyncio
async def test_a_company_you_are_not_in_can_be_deleted_from_the_list(client):
    """The session stays in the first company; Zenith is gone from the list and appears under deleted."""
    first, zenith = await _two_companies(client, "rc_chidi1@example.com")

    resp = await _delete_by_id(client, first, zenith["organization"]["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted_organization_id": zenith["organization"]["id"], "session_opened": False}
    # The session he is in is untouched.
    assert (await client.get(MEMBERSHIPS, headers=_h(first))).status_code == 200
    me = await client.get(f"{AUTH}/me", headers=_h(first))
    assert [m["organization"]["id"] for m in me.json()["memberships"]] == [first["organization"]["id"]]
    deleted = await client.get(DELETED, headers=_h(first))
    assert [(d["organization_id"], d["name"]) for d in deleted.json()["data"]] == [(zenith["organization"]["id"], "Zenith Foods")]


@pytest.mark.asyncio
async def test_you_cannot_delete_someone_elses_company_by_id(client):
    """A stranger who knows the company id is refused, and nothing is deleted."""
    owner, zenith = await _two_companies(client, "rc_owner2@example.com")
    stranger = await register_verified_and_login(client, email="rc_stranger2@example.com")
    await client.post(CREATE, json={"name": "Stranger Ltd"}, headers=_h(stranger))

    resp = await _delete_by_id(client, stranger, zenith["organization"]["id"])

    assert resp.status_code == 403
    assert (await client.get(MEMBERSHIPS, headers=_h(zenith))).status_code == 200


@pytest.mark.asyncio
async def test_a_non_owner_member_cannot_delete_by_id(client, monkeypatch):
    """An HR administrator of Zenith who is not its owner is refused."""
    owner, zenith = await _two_companies(client, "rc_owner3@example.com")
    hr = await register_verified_and_login(client, email="rc_hr3@example.com")
    await client.post(CREATE, json={"name": "Hr Own Ltd"}, headers=_h(hr))
    await join_existing(client, monkeypatch, zenith, "rc_hr3@example.com", "hr_administrator")

    resp = await _delete_by_id(client, hr, zenith["organization"]["id"])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_restore_brings_back_the_company_and_the_people_who_lost_access(client, db_session, monkeypatch):
    owner, zenith = await _two_companies(client, "rc_chidi4@example.com")
    org_id = zenith["organization"]["id"]
    kept = await register_verified_and_login(client, email="rc_kept4@example.com")
    gone = await register_verified_and_login(client, email="rc_gone4@example.com")
    await join_existing(client, monkeypatch, zenith, "rc_kept4@example.com", "employee")
    await join_existing(client, monkeypatch, zenith, "rc_gone4@example.com", "employee")
    kept_in_zenith = await _in_company(client, kept, org_id)
    # HR removed this person BEFORE the deletion: restoring must not reopen their access.
    team = await client.get(MEMBERSHIPS, headers=_h(zenith))
    gone_membership = [m for m in team.json()["data"] if m["user"]["email"] == "rc_gone4@example.com"][0]
    removed = await client.patch(
        f"{MEMBERSHIPS}/{gone_membership['id']}", json={"is_deactivated": True}, headers=_h(zenith)
    )
    assert removed.status_code == 200
    assert (await _delete_by_id(client, owner, org_id)).status_code == 200
    assert (await client.get(MEMBERSHIPS, headers=_h(kept_in_zenith))).status_code == 401
    commit_like_production(db_session, monkeypatch)

    resp = await client.post(RESTORE, json={"organization_id": org_id}, headers=_h(owner))

    assert resp.status_code == 200, resp.text
    # Listed again, and not under "deleted" any more.
    me = await client.get(f"{AUTH}/me", headers=_h(owner))
    assert org_id in [m["organization"]["id"] for m in me.json()["memberships"]]
    assert (await client.get(DELETED, headers=_h(owner))).json()["data"] == []
    # The teammate who lost access with the deletion can enter again; the one removed earlier cannot.
    # (An employee may not list the team, so 403 is the "let in" answer; 401 would mean no access.)
    assert (await client.get(MEMBERSHIPS, headers=_h(kept_in_zenith))).status_code == 403
    gone_switch = await client.post(f"{AUTH}/switch-organization", json={"organization_id": org_id}, headers=_h(gone))
    assert gone_switch.status_code == 401
    # The owner enters it too.
    assert (await client.get(MEMBERSHIPS, headers=_h(zenith))).status_code == 200


@pytest.mark.asyncio
async def test_only_the_owner_sees_and_restores_a_deleted_company(client, monkeypatch):
    owner, zenith = await _two_companies(client, "rc_chidi5@example.com")
    org_id = zenith["organization"]["id"]
    mate = await register_verified_and_login(client, email="rc_mate5@example.com")
    await join_existing(client, monkeypatch, zenith, "rc_mate5@example.com", "hr_administrator")
    assert (await _delete_by_id(client, owner, org_id)).status_code == 200

    assert (await client.get(DELETED, headers=_h(mate))).json()["data"] == []
    refused = await client.post(RESTORE, json={"organization_id": org_id}, headers=_h(mate))
    assert refused.status_code == 403


@pytest.mark.asyncio
async def test_restoring_a_company_that_is_not_deleted_is_refused(client):
    owner, zenith = await _two_companies(client, "rc_chidi6@example.com")

    resp = await client.post(RESTORE, json={"organization_id": zenith["organization"]["id"]}, headers=_h(owner))

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_restore_is_refused_when_he_already_owns_three(client):
    first, zenith = await _two_companies(client, "rc_chidi7@example.com")
    org_id = zenith["organization"]["id"]
    assert (await _delete_by_id(client, first, org_id)).status_code == 200
    assert (await client.post(CREATE, json={"name": "Second Ltd"}, headers=_h(first))).status_code == 200
    assert (await client.post(CREATE, json={"name": "Third Ltd"}, headers=_h(first))).status_code == 200

    resp = await client.post(RESTORE, json={"organization_id": org_id}, headers=_h(first))

    assert resp.status_code == 409
    assert resp.json()["code"] == "COMPANY_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_restore_is_refused_when_a_live_company_has_the_same_name(client):
    first, zenith = await _two_companies(client, "rc_chidi8@example.com")
    org_id = zenith["organization"]["id"]
    assert (await _delete_by_id(client, first, org_id)).status_code == 200
    assert (await client.post(CREATE, json={"name": "zenith foods"}, headers=_h(first))).status_code == 200

    resp = await client.post(RESTORE, json={"organization_id": org_id}, headers=_h(first))

    assert resp.status_code == 409
    assert "with that name" in resp.json()["message"]
