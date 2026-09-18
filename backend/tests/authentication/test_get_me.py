"""HTTP-level tests for GET /me."""
import pytest

BASE = "/api/v1/auth"


@pytest.mark.asyncio
async def test_get_me_returns_user_and_memberships(client):
    from tests.conftest import register_verified_and_login

    auth = await register_verified_and_login(client, email="me_test@example.com")
    access_token = auth["access_token"]

    resp = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {access_token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "me_test@example.com"
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "hr_administrator"
    assert body["memberships"][0]["is_owner"] is True
    assert body["memberships"][0]["organization"]["id"] == auth["organization"]["id"]


@pytest.mark.asyncio
async def test_get_me_requires_authentication(client):
    resp = await client.get(f"{BASE}/me")
    assert resp.status_code == 401
