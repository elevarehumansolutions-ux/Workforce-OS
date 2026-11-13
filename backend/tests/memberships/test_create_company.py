"""Starting another company from inside the app (08_DECISIONS.md 2026-11-13, round 2).

Scenario: Chidi runs one company and wants a second. Any signed-in person may start one; he owns it
(HR administrator, founder), the session moves into it, and its data is separate from the first.
He may own at most 3 companies, and never two with the same name, so a double click cannot make two.
"""
import pytest

from tests.conftest import register_verified_and_login
from tests.memberships.join_helper import AUTH, MEMBERSHIPS, join_existing

CREATE = f"{AUTH}/create-organization"


def _h(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _create(client, login: dict, name: str):
    return await client.post(CREATE, json={"name": name}, headers=_h(login))


@pytest.mark.asyncio
async def test_a_signed_in_person_creates_a_company_and_owns_it(client):
    """The answer is a session for the new company, named as asked, with Chidi as its founder."""
    chidi = await register_verified_and_login(client, email="cc_chidi1@example.com")

    resp = await _create(client, chidi, "  Zenith Foods  ")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["organization"]["name"] == "Zenith Foods"
    assert body["organization"]["id"] != chidi["organization"]["id"]
    assert (body["membership"]["role"], body["membership"]["is_owner"]) == ("hr_administrator", True)
    # The new token acts for the new company, which has just one person: Chidi.
    team = await client.get(MEMBERSHIPS, headers=_h(body))
    assert team.status_code == 200 and team.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_both_companies_are_listed_and_the_first_is_untouched(client):
    """One login, two companies; the first still opens with its own token and keeps its own people."""
    chidi = await register_verified_and_login(client, email="cc_chidi2@example.com")
    created = (await _create(client, chidi, "Zenith Foods")).json()

    me = await client.get(f"{AUTH}/me", headers=_h(created))
    active = [m for m in me.json()["memberships"] if m["deactivated_at"] is None]
    assert len(active) == 2

    first_team = await client.get(MEMBERSHIPS, headers=_h(chidi))
    assert first_team.status_code == 200 and first_team.json()["pagination"]["total"] == 1
    # Not the same data: the second company has no Business DNA yet.
    assert (await client.get("/api/v1/business-dna", headers=_h(created))).status_code == 404


@pytest.mark.asyncio
async def test_a_name_the_person_already_owns_is_refused_whatever_the_case(client):
    """A double click, or the same name typed again: the second is refused and nothing extra is made."""
    chidi = await register_verified_and_login(client, email="cc_chidi3@example.com")
    assert (await _create(client, chidi, "Zenith Foods")).status_code == 200

    again = await _create(client, chidi, "zenith FOODS")

    assert again.status_code == 409
    assert "already have a company" in again.json()["message"]
    me = await client.get(f"{AUTH}/me", headers=_h(chidi))
    assert len(me.json()["memberships"]) == 2  # the first company and the one created, no third


@pytest.mark.asyncio
async def test_at_most_three_companies_are_owned_and_the_fourth_is_refused(client):
    """The company made at sign-up counts as the first."""
    chidi = await register_verified_and_login(client, email="cc_chidi4@example.com")
    assert (await _create(client, chidi, "Second Co")).status_code == 200
    assert (await _create(client, chidi, "Third Co")).status_code == 200

    fourth = await _create(client, chidi, "Fourth Co")

    assert fourth.status_code == 409
    assert fourth.json()["code"] == "COMPANY_LIMIT_REACHED"
    me = await client.get(f"{AUTH}/me", headers=_h(chidi))
    assert len(me.json()["memberships"]) == 3


@pytest.mark.asyncio
async def test_companies_joined_by_invite_do_not_count_toward_the_limit(client, monkeypatch):
    """Chidi was invited into two other people's companies; he can still create two of his own."""
    owner_a = await register_verified_and_login(client, email="cc_ownerA@example.com")
    owner_b = await register_verified_and_login(client, email="cc_ownerB@example.com")
    chidi = await register_verified_and_login(client, email="cc_chidi5@example.com")
    await join_existing(client, monkeypatch, owner_a, "cc_chidi5@example.com", "employee")
    await join_existing(client, monkeypatch, owner_b, "cc_chidi5@example.com", "employee")

    first = await _create(client, chidi, "Second Co")
    second = await _create(client, chidi, "Third Co")
    third = await _create(client, chidi, "Fourth Co")

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 409)


@pytest.mark.asyncio
async def test_a_company_that_someone_else_owns_with_the_same_name_is_fine(client):
    """The name rule is per person: two different people may both run a 'Zenith Foods'."""
    first = await register_verified_and_login(client, email="cc_first6@example.com")
    second = await register_verified_and_login(client, email="cc_second6@example.com")

    assert (await _create(client, first, "Zenith Foods")).status_code == 200
    assert (await _create(client, second, "Zenith Foods")).status_code == 200


@pytest.mark.asyncio
async def test_the_name_is_required_and_the_caller_must_be_signed_in(client):
    """A blank or one-letter name is a 422; without a token it is a 401."""
    chidi = await register_verified_and_login(client, email="cc_chidi7@example.com")

    assert (await _create(client, chidi, "A")).status_code == 422
    assert (await _create(client, chidi, "   ")).status_code == 422
    assert (await client.post(CREATE, json={"name": "Zenith Foods"})).status_code == 401


@pytest.mark.asyncio
async def test_creating_a_company_is_written_to_the_new_companys_audit_log(client):
    """The first line of the new company's history says who started it."""
    chidi = await register_verified_and_login(client, email="cc_chidi8@example.com")
    created = (await _create(client, chidi, "Zenith Foods")).json()

    log = await client.get("/api/v1/audit-log?entity_type=organization", headers=_h(created))

    assert log.status_code == 200
    rows = log.json()["data"]
    assert [(r["action"], r["entity_type"]) for r in rows] == [("create", "organization")]
