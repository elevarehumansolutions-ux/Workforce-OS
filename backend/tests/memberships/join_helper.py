"""A shortcut for tests that need an EXISTING account to be a member of someone's company.

Since 2026-11-13 an account that already exists is no longer added to a company the moment it
is invited: it gets a pending invite and joins by accepting it with its own password. Tests that
used "invite an existing email" to create a team member now go through that real flow here.
"""
from unittest.mock import MagicMock

MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"
DEFAULT_PASSWORD = "Password123#"  # what register_verified_and_login gives every account


def _auth(login: dict) -> dict:
    return {"Authorization": f"Bearer {login['access_token']}"}


async def invite_existing(client, monkeypatch, owner: dict, email: str, role: str):
    """The owner invites an email that already has an account. Returns (response, raw invite token)."""
    import app.modules.tenancy_identity.router as membership_router_module

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)
    resp = await client.post(MEMBERSHIPS, json={"email": email, "role": role}, headers=_auth(owner))
    token = None
    if mock_dispatch.delay.call_args is not None:
        token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    return resp, token


async def join_existing(client, monkeypatch, owner: dict, email: str, role: str, password: str = DEFAULT_PASSWORD):
    """Invite an existing account and accept for them. Returns the accept response (AuthResponse JSON)."""
    invite, token = await invite_existing(client, monkeypatch, owner, email, role)
    assert invite.status_code == 200, invite.text
    accepted = await client.post(
        f"{AUTH}/accept-invite-existing", json={"token": token, "password": password}
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()
