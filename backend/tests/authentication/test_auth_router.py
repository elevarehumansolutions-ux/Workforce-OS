"""HTTP-level tests for the auth endpoints.

Drives the real FastAPI app through ``httpx`` (real routing, request
validation, dependency injection — including get_current_user's Bearer-token
handling) rather than calling AuthService directly, the way
test_auth_service.py does. The two files cover different failure surfaces:
this one catches bugs in the router/schema/dependency wiring itself.
"""

from unittest.mock import MagicMock

import pytest

BASE = "/api/v1/auth"


@pytest.mark.asyncio
async def test_register_endpoint_returns_200_and_sets_cookie(client):
    """Registering returns the new user with an access token and sets a refresh_token cookie."""
    from tests.conftest import register_payload

    resp = await client.post(f"{BASE}/register", json=register_payload(email="router_reg@example.com"))

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "router_reg@example.com"
    assert body["access_token"]
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_register_endpoint_rejects_duplicate_email(client):
    """Registering twice with the same email returns 409 on the second attempt."""
    from tests.conftest import register_payload

    payload = register_payload(email="router_dup@example.com")
    await client.post(f"{BASE}/register", json=payload)
    resp = await client.post(f"{BASE}/register", json=payload)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_endpoint_rejects_mismatched_passwords(client):
    """Registering with password and confirm_password that don't match returns 422."""
    from tests.conftest import register_payload

    payload = register_payload(email="router_mismatch@example.com", confirm_password="Different123#")
    resp = await client.post(f"{BASE}/register", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_endpoint_rejects_weak_password(client):
    """Registering with a password that fails strength validation returns 422."""
    from tests.conftest import register_payload

    payload = register_payload(
        email="router_weak@example.com", password="weak", confirm_password="weak"
    )
    resp = await client.post(f"{BASE}/register", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_verify_email_endpoint_success(client):
    """Verifying email with the token issued at registration succeeds."""
    from tests.conftest import register_payload

    reg_resp = await client.post(f"{BASE}/register", json=register_payload(email="router_verify@example.com"))
    token = reg_resp.json()["verification_token"]

    resp = await client.post(f"{BASE}/verify-email", json={"token": token})

    assert resp.status_code == 200
    assert resp.json()["message"] == "Email verified successfully"


@pytest.mark.asyncio
async def test_verify_email_endpoint_rejects_unknown_token(client):
    """Verifying email with a token that doesn't exist returns 401."""
    resp = await client.post(f"{BASE}/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_endpoint_success(client):
    """Logging in with correct credentials after verification returns an access token, membership, and cookie."""
    from tests.conftest import register_payload

    reg_resp = await client.post(f"{BASE}/register", json=register_payload(email="router_login@example.com"))
    await client.post(f"{BASE}/verify-email", json={"token": reg_resp.json()["verification_token"]})

    resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_login@example.com", "password": "Password123#"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["membership"]["role"] == "hr_administrator"
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_endpoint_rejects_wrong_password(client):
    """Logging in with a correct email but wrong password returns 401."""
    from tests.conftest import register_payload

    await client.post(f"{BASE}/register", json=register_payload(email="router_login_wrong@example.com"))

    resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_login_wrong@example.com", "password": "WrongPassword123#"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_endpoint_rejects_unknown_email(client):
    """Logging in with an email that isn't registered returns 401."""
    resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_nobody@example.com", "password": "Password123#"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_endpoint_uses_cookie_from_login(client):
    """Refresh succeeds using the refresh_token cookie login set, returning a new bearer access token."""
    from tests.conftest import register_payload

    reg_resp = await client.post(f"{BASE}/register", json=register_payload(email="router_refresh@example.com"))
    await client.post(f"{BASE}/verify-email", json={"token": reg_resp.json()["verification_token"]})
    login_resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_refresh@example.com", "password": "Password123#"},
    )
    # Confirm login itself actually succeeded — otherwise this test would
    # still pass by silently riding on the cookie register() also sets,
    # without ever having exercised login()'s cookie at all.
    assert login_resp.status_code == 200

    # httpx's client-side cookie jar resends the refresh_token cookie
    # login just set — no explicit header needed, same as a real browser.
    resp = await client.post(f"{BASE}/refresh")

    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_endpoint_without_cookie_fails(client):
    """Calling refresh with no refresh_token cookie returns 401."""
    resp = await client.post(f"{BASE}/refresh")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_then_refresh_fails(client):
    """After logout, refresh is rejected server-side even though the client still holds the revoked cookie."""
    from tests.conftest import register_payload

    reg_resp = await client.post(f"{BASE}/register", json=register_payload(email="router_logout@example.com"))
    await client.post(f"{BASE}/verify-email", json={"token": reg_resp.json()["verification_token"]})
    login_resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_logout@example.com", "password": "Password123#"},
    )
    assert login_resp.status_code == 200

    logout_resp = await client.post(f"{BASE}/logout")
    assert logout_resp.status_code == 200

    # The revoked cookie is still attached (delete_cookie doesn't retroactively
    # invalidate it client-side in the test's cookie jar) — refresh must reject
    # it on the server side.
    refresh_resp = await client.post(f"{BASE}/refresh")
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_change_password_requires_authentication(client):
    """Calling change-password without an Authorization header returns 401."""
    resp = await client.post(
        f"{BASE}/change-password",
        json={"current_password": "Password123#", "new_password": "NewPassword456#"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_change_password_endpoint_success(client):
    """A successful password change rejects login with the old password and allows login with the new one."""
    from tests.conftest import register_payload

    reg_resp = await client.post(f"{BASE}/register", json=register_payload(email="router_changepw@example.com"))
    # get_current_user gates on account_status — a fresh registration is
    # pending_verification, which change-password (correctly) rejects.
    await client.post(f"{BASE}/verify-email", json={"token": reg_resp.json()["verification_token"]})

    login_resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_changepw@example.com", "password": "Password123#"},
    )
    access_token = login_resp.json()["access_token"]

    resp = await client.post(
        f"{BASE}/change-password",
        json={"current_password": "Password123#", "new_password": "NewPassword456#"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200

    old_login = await client.post(
        f"{BASE}/login",
        json={"email": "router_changepw@example.com", "password": "Password123#"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        f"{BASE}/login",
        json={"email": "router_changepw@example.com", "password": "NewPassword456#"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_garbage_token(client):
    """Calling change-password with a malformed bearer token returns 401."""
    resp = await client.post(
        f"{BASE}/change-password",
        json={"current_password": "Password123#", "new_password": "NewPassword456#"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resend_verification_endpoint_always_returns_200(client, monkeypatch):
    """Resend-verification returns 200 even for an email that isn't registered, to avoid leaking account existence."""
    import app.modules.auth.service as auth_service_module

    monkeypatch.setattr(auth_service_module, "dispatch_verification_email", MagicMock())

    resp = await client.post(f"{BASE}/resend-verification", json={"email": "router_resend_nobody@example.com"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_endpoint_always_returns_200(client, monkeypatch):
    """Forgot-password returns 200 even for an email that isn't registered, to avoid leaking account existence."""
    import app.modules.auth.service as auth_service_module

    monkeypatch.setattr(auth_service_module, "dispatch_password_reset_email", MagicMock())

    resp = await client.post(f"{BASE}/forgot-password", json={"email": "router_forgot_nobody@example.com"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_endpoint_full_flow(client, monkeypatch):
    """The forgot-password -> reset-password flow replaces the password, allowing login only with the new one."""
    from tests.conftest import register_payload
    import app.modules.auth.service as auth_service_module

    reg_resp = await client.post(f"{BASE}/register", json=register_payload(email="router_reset@example.com"))
    await client.post(f"{BASE}/verify-email", json={"token": reg_resp.json()["verification_token"]})

    mock_dispatch = MagicMock()
    monkeypatch.setattr(auth_service_module, "dispatch_password_reset_email", mock_dispatch)

    await client.post(f"{BASE}/forgot-password", json={"email": "router_reset@example.com"})
    raw_token = mock_dispatch.delay.call_args.args[0]

    resp = await client.post(
        f"{BASE}/reset-password",
        json={"token": raw_token, "new_password": "BrandNewPass789#"},
    )
    assert resp.status_code == 200

    login_resp = await client.post(
        f"{BASE}/login",
        json={"email": "router_reset@example.com", "password": "BrandNewPass789#"},
    )
    assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_endpoint_rejects_bad_token(client):
    """Reset-password with a token that doesn't exist returns 401."""
    resp = await client.post(
        f"{BASE}/reset-password",
        json={"token": "not-a-real-token", "new_password": "BrandNewPass789#"},
    )
    assert resp.status_code == 401
