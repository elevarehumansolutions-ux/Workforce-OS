"""One login, several companies (08_DECISIONS.md 2026-11-13).

Scenario: Chidi signed up by mistake (so he owns an empty company of his own). Adaeze, who runs
Zenith, invites his email. He is NOT added behind his back: he gets an invite, sees which company
it is for, confirms with his own password, and can then switch between his company and Zenith.
"""
from unittest.mock import MagicMock

import pytest

from tests.conftest import register_payload, register_verified_and_login
from tests.memberships.join_helper import AUTH, MEMBERSHIPS, invite_existing, join_existing


def _h(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def _preview(client, token: str):
    return await client.post(f"{AUTH}/invite-preview", json={"token": token})


# ---------------------------------------------------------------- the optional name

@pytest.mark.asyncio
async def test_a_name_typed_on_the_invite_is_prefilled_on_the_accept_page(client, monkeypatch):
    """Invite Team has an optional name; the preview returns it so the invitee does not type it again."""
    import app.modules.tenancy_identity.router as membership_router

    owner = await register_verified_and_login(client, email="mc_owner1@example.com")
    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(
        MEMBERSHIPS,
        json={"email": "mc_new1@example.com", "role": "manager", "full_name": "Chidi Okafor"},
        headers=_h(owner),
    )
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]

    preview = await _preview(client, token)

    assert preview.status_code == 200
    body = preview.json()
    assert body["email"] == "mc_new1@example.com"
    assert body["invitee_name"] == "Chidi Okafor"
    assert body["role"] == "manager"
    assert body["account_exists"] is False


@pytest.mark.asyncio
async def test_the_name_is_optional(client, monkeypatch):
    """Without a name the preview says null and the page asks for it."""
    owner = await register_verified_and_login(client, email="mc_owner2@example.com")
    _, token = await invite_existing(client, monkeypatch, owner, "mc_nobody2@example.com", "employee")

    assert (await _preview(client, token)).json()["invitee_name"] is None


@pytest.mark.asyncio
async def test_an_invite_sent_from_add_employee_carries_the_employee_name(client, monkeypatch):
    """HR typed Chidi's name once, on the employee record: the invite knows it."""
    import app.modules.organization.router as employee_router
    import app.modules.tenancy_identity.router as membership_router
    from datetime import date

    owner = await register_verified_and_login(client, email="mc_owner3@example.com")
    h = _h(owner)
    mock_dispatch = MagicMock()
    monkeypatch.setattr(employee_router, "dispatch_invite_email", mock_dispatch)
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    dept = (await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)).json()["id"]
    position = (await client.post("/api/v1/positions", json={"department_id": dept, "title": "Rep"}, headers=h)).json()["id"]

    await client.post(
        "/api/v1/employees",
        json={
            "position_id": position, "first_name": "Chidi", "last_name": "Okafor",
            "work_email": "mc_chidi3@example.com", "start_date": date.today().isoformat(),
            "grant_login_access": True, "role": "employee",
        },
        headers=h,
    )
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]

    assert (await _preview(client, token)).json()["invitee_name"] == "Chidi Okafor"


# ---------------------------------------------------------------- the preview

@pytest.mark.asyncio
async def test_the_preview_says_when_the_email_already_has_an_account(client, monkeypatch):
    """Then the page asks only for the existing password."""
    owner = await register_verified_and_login(client, email="mc_owner4@example.com")
    await register_verified_and_login(client, email="mc_chidi4@example.com")
    _, token = await invite_existing(client, monkeypatch, owner, "mc_chidi4@example.com", "employee")

    assert (await _preview(client, token)).json()["account_exists"] is True


@pytest.mark.asyncio
async def test_the_preview_refuses_an_unknown_or_used_link(client, monkeypatch):
    owner = await register_verified_and_login(client, email="mc_owner5@example.com")
    await register_verified_and_login(client, email="mc_chidi5@example.com")
    assert (await _preview(client, "not-a-real-token")).status_code == 401

    await join_existing(client, monkeypatch, owner, "mc_chidi5@example.com", "employee")
    # the link was used when they joined
    _, token = await invite_existing(client, monkeypatch, owner, "mc_other5@example.com", "employee")
    used = await client.post(
        f"{AUTH}/accept-invite",
        json={"token": token, "full_name": "Other Person", "password": "Password123#", "confirm_password": "Password123#"},
    )
    assert used.status_code == 200
    assert (await _preview(client, token)).status_code == 400


# ---------------------------------------------------------------- accepting with an existing account

@pytest.mark.asyncio
async def test_accepting_needs_the_existing_accounts_own_password(client, monkeypatch):
    """The link alone is not enough: a wrong password changes nothing."""
    owner = await register_verified_and_login(client, email="mc_owner6@example.com")
    await register_verified_and_login(client, email="mc_chidi6@example.com")
    _, token = await invite_existing(client, monkeypatch, owner, "mc_chidi6@example.com", "employee")

    wrong = await client.post(f"{AUTH}/accept-invite-existing", json={"token": token, "password": "Wrong-password1#"})

    assert wrong.status_code == 401
    team = await client.get(MEMBERSHIPS, headers=_h(owner))
    assert team.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_accepting_joins_the_company_and_the_session_is_for_that_company(client, monkeypatch):
    """Chidi now belongs to two companies, and the answer to his accept is a session for Zenith."""
    owner = await register_verified_and_login(client, email="mc_owner7@example.com")
    chidi = await register_verified_and_login(client, email="mc_chidi7@example.com")

    joined = await join_existing(client, monkeypatch, owner, "mc_chidi7@example.com", "hr_administrator")

    assert joined["organization"]["id"] == owner["organization"]["id"]
    assert joined["organization"]["id"] != chidi["organization"]["id"]
    # The new token acts for Zenith: Chidi (HR there) can read Zenith's team.
    team = await client.get(MEMBERSHIPS, headers=_h(joined))
    assert team.status_code == 200 and team.json()["pagination"]["total"] == 2
    me = await client.get(f"{AUTH}/me", headers=_h(joined))
    assert len([m for m in me.json()["memberships"] if m["deactivated_at"] is None]) == 2


@pytest.mark.asyncio
async def test_keep_current_company_joins_without_moving_the_session(client, monkeypatch):
    """Chidi is mid-setup in his own company. Accepting Zenith's invite must not move him out of it."""
    owner = await register_verified_and_login(client, email="mc_owner7b@example.com")
    chidi = await register_verified_and_login(client, email="mc_chidi7b@example.com")
    _, token = await invite_existing(client, monkeypatch, owner, "mc_chidi7b@example.com", "employee")

    accepted = await client.post(
        f"{AUTH}/accept-invite-existing",
        json={"token": token, "password": "Password123#", "keep_current_company": True},
    )

    assert accepted.status_code == 200
    body = accepted.json()
    assert body["session_opened"] is False
    assert "access_token" not in body  # no new token...
    assert "refresh_token" not in accepted.headers.get("set-cookie", "")  # ...and no new cookie
    assert body["organization"]["id"] == owner["organization"]["id"]
    # He did join: both companies are on his list, and his own token still works for his own company.
    me = await client.get(f"{AUTH}/me", headers=_h(chidi))
    assert len([m for m in me.json()["memberships"] if m["deactivated_at"] is None]) == 2
    own_team = await client.get(MEMBERSHIPS, headers=_h(chidi))
    assert own_team.status_code == 200 and own_team.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_the_same_invite_cannot_be_accepted_twice(client, monkeypatch):
    owner = await register_verified_and_login(client, email="mc_owner8@example.com")
    await register_verified_and_login(client, email="mc_chidi8@example.com")
    _, token = await invite_existing(client, monkeypatch, owner, "mc_chidi8@example.com", "employee")
    body = {"token": token, "password": "Password123#"}

    first = await client.post(f"{AUTH}/accept-invite-existing", json=body)
    second = await client.post(f"{AUTH}/accept-invite-existing", json=body)

    assert (first.status_code, second.status_code) == (200, 400)


@pytest.mark.asyncio
async def test_an_account_that_never_verified_its_email_is_verified_by_the_invite(client, monkeypatch):
    """They signed up by mistake and never clicked the email. The invite reached the same inbox, so it counts."""
    owner = await register_verified_and_login(client, email="mc_owner9@example.com")
    payload = register_payload(email="mc_chidi9@example.com")
    await client.post(f"{AUTH}/register", json=payload)  # never verified
    _, token = await invite_existing(client, monkeypatch, owner, "mc_chidi9@example.com", "employee")

    accepted = await client.post(
        f"{AUTH}/accept-invite-existing", json={"token": token, "password": payload["password"]}
    )

    assert accepted.status_code == 200
    login = await client.post(f"{AUTH}/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200


# ---------------------------------------------------------------- switching company

@pytest.mark.asyncio
async def test_switching_company_gives_a_session_for_the_other_company(client, monkeypatch):
    """Chidi logs in to his own empty company (his earliest); switching opens Zenith, and back again."""
    owner = await register_verified_and_login(client, email="mc_owner10@example.com")
    chidi = await register_verified_and_login(client, email="mc_chidi10@example.com")
    await join_existing(client, monkeypatch, owner, "mc_chidi10@example.com", "hr_administrator")
    login = await client.post(f"{AUTH}/login", json={"email": "mc_chidi10@example.com", "password": "Password123#"})
    assert login.json()["organization"]["id"] == chidi["organization"]["id"]  # lands in his own first
    own_team = await client.get(MEMBERSHIPS, headers=_h(login.json()))
    assert own_team.json()["pagination"]["total"] == 1

    switched = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": owner["organization"]["id"]}, headers=_h(login.json())
    )

    assert switched.status_code == 200
    assert switched.json()["organization"]["id"] == owner["organization"]["id"]
    zenith_team = await client.get(MEMBERSHIPS, headers=_h(switched.json()))
    assert zenith_team.json()["pagination"]["total"] == 2

    back = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": chidi["organization"]["id"]}, headers=_h(switched.json())
    )
    assert back.json()["organization"]["id"] == chidi["organization"]["id"]


@pytest.mark.asyncio
async def test_you_cannot_switch_into_a_company_you_do_not_belong_to(client):
    owner = await register_verified_and_login(client, email="mc_owner11@example.com")
    stranger = await register_verified_and_login(client, email="mc_stranger11@example.com")

    resp = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": owner["organization"]["id"]}, headers=_h(stranger)
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_you_cannot_switch_into_a_company_that_deactivated_you(client, monkeypatch):
    owner = await register_verified_and_login(client, email="mc_owner12@example.com")
    await register_verified_and_login(client, email="mc_chidi12@example.com")
    joined = await join_existing(client, monkeypatch, owner, "mc_chidi12@example.com", "employee")
    await client.patch(
        f"{MEMBERSHIPS}/{joined['membership']['id']}", json={"is_deactivated": True}, headers=_h(owner)
    )
    login = await client.post(f"{AUTH}/login", json={"email": "mc_chidi12@example.com", "password": "Password123#"})

    resp = await client.post(
        f"{AUTH}/switch-organization", json={"organization_id": owner["organization"]["id"]}, headers=_h(login.json())
    )

    assert resp.status_code == 401
