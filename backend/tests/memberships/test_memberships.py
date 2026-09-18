"""HTTP-level tests for POST/GET/PATCH /memberships and POST /auth/accept-invite."""
from unittest.mock import MagicMock

import pytest

MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_invite_teammate_adds_existing_user_immediately(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner1@example.com")
    await register_verified_and_login(client, email="other1@example.com")  # owner of a separate org

    resp = await client.post(
        MEMBERSHIPS,
        json={"email": "other1@example.com", "role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "added"
    assert body["membership"]["role"] == "manager"
    assert body["membership"]["user"]["email"] == "other1@example.com"


@pytest.mark.asyncio
async def test_invite_teammate_rejects_duplicate_membership(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner2@example.com")
    await register_verified_and_login(client, email="other2@example.com")

    await client.post(
        MEMBERSHIPS,
        json={"email": "other2@example.com", "role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )
    resp = await client.post(
        MEMBERSHIPS,
        json={"email": "other2@example.com", "role": "employee"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invite_teammate_creates_pending_invite_for_new_email(client, monkeypatch):
    import app.modules.tenancy_identity.router as membership_router_module
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner3@example.com")

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    resp = await client.post(
        MEMBERSHIPS,
        json={"email": "brand_new@example.com", "role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "invited"
    assert body["invite"]["email"] == "brand_new@example.com"
    mock_dispatch.delay.assert_called_once()
    invite_link = mock_dispatch.delay.call_args.args[1]
    assert "token=" in invite_link


@pytest.mark.asyncio
async def test_accept_invite_creates_account_and_logs_in(client, monkeypatch):
    import app.modules.tenancy_identity.router as membership_router_module
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner4@example.com")

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": "invitee@example.com", "role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]

    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Invited Person",
            "password": "InviteePass123#",
            "confirm_password": "InviteePass123#",
        },
    )

    assert accept_resp.status_code == 200
    body = accept_resp.json()
    assert body["user"]["email"] == "invitee@example.com"
    # The invite proves email ownership — no separate verify-email step.
    assert body["user"]["account_status"] == "verified"
    assert body["membership"]["role"] == "manager"
    assert body["organization"]["id"] == owner["organization"]["id"]

    login_resp = await client.post(
        f"{AUTH}/login",
        json={"email": "invitee@example.com", "password": "InviteePass123#"},
    )
    assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_accept_invite_rejects_reused_token(client, monkeypatch):
    import app.modules.tenancy_identity.router as membership_router_module
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner5@example.com")
    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": "invitee5@example.com", "role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]

    payload = {
        "token": raw_token,
        "full_name": "Invited Person",
        "password": "InviteePass123#",
        "confirm_password": "InviteePass123#",
    }
    first = await client.post(f"{AUTH}/accept-invite", json=payload)
    assert first.status_code == 200

    second = await client.post(f"{AUTH}/accept-invite", json=payload)
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_accept_invite_rejects_unknown_token(client):
    resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": "not-a-real-token",
            "full_name": "Nobody",
            "password": "SomePass123#",
            "confirm_password": "SomePass123#",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_memberships_returns_team(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner6@example.com")
    await register_verified_and_login(client, email="other6@example.com")
    await client.post(
        MEMBERSHIPS,
        json={"email": "other6@example.com", "role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )

    resp = await client.get(MEMBERSHIPS, headers=_auth_header(owner["access_token"]))

    assert resp.status_code == 200
    emails = {m["user"]["email"] for m in resp.json()}
    assert emails == {"owner6@example.com", "other6@example.com"}


@pytest.mark.asyncio
async def test_list_memberships_requires_hr_admin_role(client, monkeypatch):
    """An employee-role member (via accept-invite, so their only membership
    is this org — no earliest-joined-default ambiguity) can't list the team."""
    import app.modules.tenancy_identity.router as membership_router_module
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner7@example.com")
    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": "employee7@example.com", "role": "employee"},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Employee Person",
            "password": "EmployeePass123#",
            "confirm_password": "EmployeePass123#",
        },
    )
    employee_token = accept_resp.json()["access_token"]

    resp = await client.get(MEMBERSHIPS, headers=_auth_header(employee_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_membership_changes_role(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner8@example.com")
    await register_verified_and_login(client, email="other8@example.com")
    add_resp = await client.post(
        MEMBERSHIPS,
        json={"email": "other8@example.com", "role": "employee"},
        headers=_auth_header(owner["access_token"]),
    )
    membership_id = add_resp.json()["membership"]["id"]

    resp = await client.patch(
        f"{MEMBERSHIPS}/{membership_id}",
        json={"role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_patch_membership_deactivates_teammate(client, monkeypatch):
    """Uses accept-invite, not register_verified_and_login, to create the
    teammate — a directly-registered user always has their own founding org
    as an extra membership (can't reach zero active memberships that way);
    an accept-invite user genuinely has only the one invited membership,
    which is what this test actually needs to exercise deactivation down to
    zero active memberships anywhere."""
    from tests.conftest import register_verified_and_login
    import app.modules.tenancy_identity.router as membership_router_module

    owner = await register_verified_and_login(client, email="owner9@example.com")

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)
    await client.post(
        MEMBERSHIPS,
        json={"email": "other9@example.com", "role": "employee"},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Other Person",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    membership_id = accept_resp.json()["membership"]["id"]

    resp = await client.patch(
        f"{MEMBERSHIPS}/{membership_id}",
        json={"is_deactivated": True},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    # Scoped to the membership (08_DECISIONS.md 2026-09-18), not the user's
    # account globally — no more account_status touched by this endpoint.
    assert resp.json()["deactivated_at"] is not None

    # other9 genuinely has exactly one membership (accept-invite creates no
    # founding org of its own), and it's now the one just deactivated, so
    # they have zero active memberships anywhere — login correctly still
    # fails, but for that specific reason, not a global account lock.
    login_resp = await client.post(
        f"{AUTH}/login",
        json={"email": "other9@example.com", "password": "Password123#"},
    )
    assert login_resp.status_code == 403
    assert login_resp.json()["code"] == "NO_ACTIVE_MEMBERSHIP"


@pytest.mark.asyncio
async def test_deactivation_does_not_affect_a_different_organization(client):
    """The actual point of scoping this to the membership: someone deactivated
    from Org A keeps full, working access to Org B."""
    from tests.conftest import register_verified_and_login

    owner_a = await register_verified_and_login(client, email="owner_a@example.com")
    owner_b = await register_verified_and_login(client, email="owner_b@example.com")
    shared_user = await register_verified_and_login(client, email="shared_user@example.com")

    for owner in (owner_a, owner_b):
        invite_resp = await client.post(
            MEMBERSHIPS,
            json={"email": "shared_user@example.com", "role": "employee"},
            headers=_auth_header(owner["access_token"]),
        )
        assert invite_resp.status_code == 200, invite_resp.json()

    # Deactivate shared_user from Org A only.
    memberships_in_a = await client.get(MEMBERSHIPS, headers=_auth_header(owner_a["access_token"]))
    membership_id_in_a = next(
        m["id"] for m in memberships_in_a.json() if m["user"]["email"] == "shared_user@example.com"
    )
    deactivate_resp = await client.patch(
        f"{MEMBERSHIPS}/{membership_id_in_a}",
        json={"is_deactivated": True},
        headers=_auth_header(owner_a["access_token"]),
    )
    assert deactivate_resp.status_code == 200

    # shared_user can still log in at all — deactivation from one org didn't
    # touch their account globally (register_verified_and_login's own
    # founding org, created before either invite, is what login lands them
    # in here — earliest and still active — not a claim about Org A/B).
    login_resp = await client.post(
        f"{AUTH}/login",
        json={"email": "shared_user@example.com", "password": "Password123#"},
    )
    assert login_resp.status_code == 200

    # The actual point: GET /me shows Org A as deactivated and Org B as
    # still fully active, proving deactivation didn't leak across orgs.
    me_resp = await client.get(f"{AUTH}/me", headers=_auth_header(login_resp.json()["access_token"]))
    memberships_by_org = {m["organization"]["id"]: m for m in me_resp.json()["memberships"]}
    assert memberships_by_org[owner_a["organization"]["id"]]["deactivated_at"] is not None
    assert memberships_by_org[owner_b["organization"]["id"]]["deactivated_at"] is None


@pytest.mark.asyncio
async def test_patch_membership_rejects_self_target(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner10@example.com")
    own_membership_id = owner["membership"]["id"]

    resp = await client.patch(
        f"{MEMBERSHIPS}/{own_membership_id}",
        json={"role": "manager"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_membership_rejects_deactivating_owner(client, monkeypatch):
    """Even a second HR admin (not the Owner themself) can't deactivate the Owner."""
    import app.modules.tenancy_identity.router as membership_router_module
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner11@example.com")
    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": "coadmin11@example.com", "role": "hr_administrator"},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Co Admin",
            "password": "CoAdminPass123#",
            "confirm_password": "CoAdminPass123#",
        },
    )
    coadmin_token = accept_resp.json()["access_token"]
    owner_membership_id = owner["membership"]["id"]

    resp = await client.patch(
        f"{MEMBERSHIPS}/{owner_membership_id}",
        json={"is_deactivated": True},
        headers=_auth_header(coadmin_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_membership_not_found_across_orgs(client):
    """A membership id from a different org is indistinguishable from a
    nonexistent one — get_membership_by_id is scoped by RLS automatically,
    the router never has to check "does this belong to my org" by hand."""
    from tests.conftest import register_verified_and_login

    owner_a = await register_verified_and_login(client, email="orga@example.com")
    owner_b = await register_verified_and_login(client, email="orgb@example.com")

    resp = await client.patch(
        f"{MEMBERSHIPS}/{owner_b['membership']['id']}",
        json={"role": "manager"},
        headers=_auth_header(owner_a["access_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_membership_requires_at_least_one_field(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="owner12@example.com")
    await register_verified_and_login(client, email="other12@example.com")
    add_resp = await client.post(
        MEMBERSHIPS,
        json={"email": "other12@example.com", "role": "employee"},
        headers=_auth_header(owner["access_token"]),
    )
    membership_id = add_resp.json()["membership"]["id"]

    resp = await client.patch(
        f"{MEMBERSHIPS}/{membership_id}",
        json={},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_memberships_endpoints_require_authentication(client):
    resp1 = await client.get(MEMBERSHIPS)
    assert resp1.status_code == 401

    resp2 = await client.post(MEMBERSHIPS, json={"email": "x@example.com", "role": "employee"})
    assert resp2.status_code == 401
