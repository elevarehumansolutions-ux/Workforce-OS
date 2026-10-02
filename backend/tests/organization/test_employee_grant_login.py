"""HTTP-level tests for giving employees login access.

Covers ``POST /employees/{id}/grant-login`` ("Send invite", also the resend
action), the ``grant_login_access`` checkbox on ``POST /employees``, the
invite carrying its employee through ``POST /auth/accept-invite``, and
``GET /employees/unlinked-members`` (08_DECISIONS.md 2026-10-01).
"""
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def invite_emails(monkeypatch) -> MagicMock:
    """Capture invite emails queued by both the employee and membership routes."""
    import app.modules.organization.router as employee_router
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(employee_router, "dispatch_invite_email", mock_dispatch)
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    return mock_dispatch


def _token_from(mock_dispatch: MagicMock, call_index: int = -1) -> str:
    return mock_dispatch.delay.call_args_list[call_index].args[1].split("token=")[1]


async def _accept(client, token: str, name: str = "New Hire"):
    return await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": token,
            "full_name": name,
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )


async def _setup_position(client, h) -> str:
    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "Engineer"}, headers=h)
    return pos.json()["id"]


async def _employee(client, h, position_id: str, email: str, **extra):
    body = {
        "position_id": position_id,
        "first_name": "Test",
        "last_name": "Person",
        "work_email": email,
        "start_date": date.today().isoformat(),
        **extra,
    }
    return await client.post(EMPLOYEES, json=body, headers=h)


async def _owner(client, email: str):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email=email)
    return owner, _auth_header(owner["access_token"])


@pytest.mark.asyncio
async def test_grant_login_to_a_new_email_sends_an_invite_and_accepting_links_the_employee(client, invite_emails):
    """The whole flow: Send invite, click the link, land attached to the employee record."""
    owner, h = await _owner(client, "gl_owner1@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "chidi1@example.com")).json()

    resp = await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "invited"
    assert resp.json()["employee"]["user_id"] is None
    invite_emails.delay.assert_called_once()
    assert invite_emails.delay.call_args.args[0] == "chidi1@example.com"

    accepted = await _accept(client, _token_from(invite_emails))
    assert accepted.status_code == 200
    fetched = await client.get(f"{EMPLOYEES}/{emp['id']}", headers=h)
    assert fetched.json()["user_id"] == accepted.json()["user"]["id"]


@pytest.mark.asyncio
async def test_grant_login_resend_replaces_the_pending_invite(client, invite_emails):
    """Sending again kills the earlier link and issues a fresh one that works."""
    owner, h = await _owner(client, "gl_owner2@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "chidi2@example.com")).json()
    await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)
    await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)
    assert invite_emails.delay.call_count == 2

    old = await _accept(client, _token_from(invite_emails, 0))
    new = await _accept(client, _token_from(invite_emails, 1))

    assert old.status_code == 400
    assert new.status_code == 200
    fetched = await client.get(f"{EMPLOYEES}/{emp['id']}", headers=h)
    assert fetched.json()["user_id"] == new.json()["user"]["id"]


@pytest.mark.asyncio
async def test_grant_login_to_an_existing_account_links_immediately_without_email(client, invite_emails):
    """An email that already has an account elsewhere is added to the org and linked on the spot."""
    owner, h = await _owner(client, "gl_owner3@example.com")
    other, _ = await _owner(client, "gl_existing3@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "gl_existing3@example.com")).json()

    resp = await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "manager"}, headers=h)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "added"
    assert resp.json()["employee"]["user_id"] == other["user"]["id"]
    invite_emails.delay.assert_not_called()


@pytest.mark.asyncio
async def test_grant_login_for_an_existing_org_member_links_without_changing_their_role(client, invite_emails):
    """The Owner (already an active member) can be linked to their own employee record."""
    owner, h = await _owner(client, "gl_owner4@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "gl_owner4@example.com")).json()

    resp = await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "linked"
    assert resp.json()["employee"]["user_id"] == owner["user"]["id"]
    invite_emails.delay.assert_not_called()
    members = await client.get(MEMBERSHIPS, headers=h)
    mine = [m for m in members.json()["data"] if m["user"]["email"] == "gl_owner4@example.com"]
    assert mine[0]["role"] == "hr_administrator"


@pytest.mark.asyncio
async def test_grant_login_refused_when_employee_already_has_a_login(client, invite_emails):
    """An employee with a login can't be given another."""
    owner, h = await _owner(client, "gl_owner5@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "gl_owner5@example.com", user_id=owner["user"]["id"])).json()

    resp = await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)

    assert resp.status_code == 409
    assert resp.json()["code"] == "EMPLOYEE_ALREADY_HAS_LOGIN"


@pytest.mark.asyncio
async def test_grant_login_refused_for_an_offboarded_employee(client, invite_emails):
    """An offboarded employee must be reinstated before getting login access."""
    owner, h = await _owner(client, "gl_owner6@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "chidi6@example.com")).json()
    assert (await client.post(f"{EMPLOYEES}/{emp['id']}/offboard", headers=h)).status_code == 200

    resp = await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)

    assert resp.status_code == 422
    invite_emails.delay.assert_not_called()


@pytest.mark.asyncio
async def test_accepting_an_invite_still_works_if_the_employee_was_offboarded_meanwhile(client, invite_emails):
    """Acceptance never fails because of the employee link — it just skips linking."""
    owner, h = await _owner(client, "gl_owner7@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "chidi7@example.com")).json()
    await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)
    await client.post(f"{EMPLOYEES}/{emp['id']}/offboard", headers=h)

    accepted = await _accept(client, _token_from(invite_emails))

    assert accepted.status_code == 200
    fetched = await client.get(f"{EMPLOYEES}/{emp['id']}", headers=h)
    assert fetched.json()["user_id"] is None


@pytest.mark.asyncio
async def test_accepting_an_invite_does_not_override_a_login_linked_meanwhile(client, invite_emails):
    """If HR linked someone else by hand before the invite was accepted, that link stands."""
    owner, h = await _owner(client, "gl_owner8@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "chidi8@example.com")).json()
    await client.post(f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h)
    link = await client.post(
        f"{EMPLOYEES}/{emp['id']}/link-user", json={"user_id": owner["user"]["id"]}, headers=h
    )
    assert link.status_code == 200

    accepted = await _accept(client, _token_from(invite_emails))

    assert accepted.status_code == 200
    fetched = await client.get(f"{EMPLOYEES}/{emp['id']}", headers=h)
    assert fetched.json()["user_id"] == owner["user"]["id"]


@pytest.mark.asyncio
async def test_create_employee_with_the_checkbox_sends_an_invite(client, invite_emails):
    """Add Employee with grant_login_access invites the person in the same call."""
    owner, h = await _owner(client, "gl_owner9@example.com")
    position_id = await _setup_position(client, h)

    resp = await _employee(client, h, position_id, "chidi9@example.com", grant_login_access=True, role="manager")

    assert resp.status_code == 200
    invite_emails.delay.assert_called_once()
    accepted = await _accept(client, _token_from(invite_emails))
    fetched = await client.get(f"{EMPLOYEES}/{resp.json()['id']}", headers=h)
    assert fetched.json()["user_id"] == accepted.json()["user"]["id"]
    assert accepted.json()["membership"]["role"] == "manager"


@pytest.mark.asyncio
async def test_checkbox_requires_a_role_and_refuses_a_user_id(client, invite_emails):
    """grant_login_access without a role, or combined with user_id, is rejected as a bad request."""
    owner, h = await _owner(client, "gl_owner10@example.com")
    position_id = await _setup_position(client, h)

    no_role = await _employee(client, h, position_id, "a10@example.com", grant_login_access=True)
    both = await _employee(
        client, h, position_id, "b10@example.com",
        grant_login_access=True, role="employee", user_id=owner["user"]["id"],
    )

    assert no_role.status_code == 422
    assert both.status_code == 422
    listed = await client.get(EMPLOYEES, headers=h)
    assert listed.json()["data"] == []


@pytest.mark.asyncio
async def test_create_with_the_checkbox_is_all_or_nothing(client, invite_emails):
    """If granting login fails, the employee isn't created either."""
    owner, h = await _owner(client, "gl_owner11@example.com")
    position_id = await _setup_position(client, h)
    first = await _employee(client, h, position_id, "gl_owner11@example.com", user_id=owner["user"]["id"])
    assert first.status_code == 200

    resp = await _employee(
        client, h, position_id, "gl_owner11@example.com", grant_login_access=True, role="employee"
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "EMPLOYEE_USER_ALREADY_LINKED"
    listed = await client.get(EMPLOYEES, headers=h)
    assert len(listed.json()["data"]) == 1


@pytest.mark.asyncio
async def test_grant_login_requires_hr_admin_and_stays_inside_the_org(client, invite_emails):
    """A manager gets 403; another org's admin gets 404 for an employee they can't see."""
    owner, h = await _owner(client, "gl_owner12@example.com")
    outsider, h_out = await _owner(client, "gl_outsider12@example.com")
    position_id = await _setup_position(client, h)
    emp = (await _employee(client, h, position_id, "chidi12@example.com")).json()
    await client.post(MEMBERSHIPS, json={"email": "gl_mgr12@example.com", "role": "manager"}, headers=h)
    manager = await _accept(client, _token_from(invite_emails))

    as_manager = await client.post(
        f"{EMPLOYEES}/{emp['id']}/grant-login",
        json={"role": "employee"},
        headers=_auth_header(manager.json()["access_token"]),
    )
    as_outsider = await client.post(
        f"{EMPLOYEES}/{emp['id']}/grant-login", json={"role": "employee"}, headers=h_out
    )
    unknown = await client.post(f"{EMPLOYEES}/{uuid.uuid4()}/grant-login", json={"role": "employee"}, headers=h)

    assert as_manager.status_code == 403
    assert as_outsider.status_code == 404
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_unlinked_members_lists_only_active_members_without_an_employee(client, invite_emails):
    """Members drop off the list once they have an employee record."""
    owner, h = await _owner(client, "gl_owner13@example.com")
    position_id = await _setup_position(client, h)
    await client.post(MEMBERSHIPS, json={"email": "gl_mgr13@example.com", "role": "manager"}, headers=h)
    await _accept(client, _token_from(invite_emails))

    before = await client.get(f"{EMPLOYEES}/unlinked-members", headers=h)
    emails_before = {m["user"]["email"] for m in before.json()["data"]}
    await _employee(client, h, position_id, "gl_owner13@example.com", user_id=owner["user"]["id"])
    after = await client.get(f"{EMPLOYEES}/unlinked-members", headers=h)
    emails_after = {m["user"]["email"] for m in after.json()["data"]}

    assert emails_before == {"gl_owner13@example.com", "gl_mgr13@example.com"}
    assert emails_after == {"gl_mgr13@example.com"}


@pytest.mark.asyncio
async def test_unlinked_members_requires_hr_admin(client, invite_emails):
    """Only HR administrators can see who is unlinked."""
    owner, h = await _owner(client, "gl_owner14@example.com")
    await client.post(MEMBERSHIPS, json={"email": "gl_mgr14@example.com", "role": "manager"}, headers=h)
    manager = await _accept(client, _token_from(invite_emails))

    resp = await client.get(
        f"{EMPLOYEES}/unlinked-members", headers=_auth_header(manager.json()["access_token"])
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_a_repeated_teammate_invite_replaces_the_pending_one(client, invite_emails):
    """Inviting a pending email again (POST /memberships) kills the first link, as the resend relies on."""
    owner, h = await _owner(client, "gl_owner15@example.com")
    for _ in range(2):
        await client.post(MEMBERSHIPS, json={"email": "gl_twice15@example.com", "role": "employee"}, headers=h)

    first = await _accept(client, _token_from(invite_emails, 0))
    second = await _accept(client, _token_from(invite_emails, 1))

    assert first.status_code == 400
    assert second.status_code == 200
