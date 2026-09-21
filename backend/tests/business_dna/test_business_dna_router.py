"""HTTP-level tests for /business-dna and /business-dna/core-values."""
import pytest

BUSINESS_DNA = "/api/v1/business-dna"
CORE_VALUES = "/api/v1/business-dna/core-values"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _invite_and_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    from unittest.mock import MagicMock
    import app.modules.tenancy_identity.router as membership_router_module

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": email, "role": role},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Test Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return accept_resp.json()


@pytest.mark.asyncio
async def test_business_dna_requires_authentication(client):
    """GET /business-dna rejects an unauthenticated request with 401."""
    resp = await client.get(BUSINESS_DNA)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_business_dna_404_before_first_upsert(client):
    """GET /business-dna 404s until the org has upserted a profile."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner1@example.com")
    resp = await client.get(BUSINESS_DNA, headers=_auth_header(owner["access_token"]))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upsert_requires_hr_admin_role(client, monkeypatch):
    """An employee-role member is rejected with 403 when upserting Business DNA."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner2@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "dna_emp2@example.com", "employee")

    resp = await client.put(
        BUSINESS_DNA, json={"vision": "See far"}, headers=_auth_header(employee["access_token"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upsert_create_then_get_roundtrip_with_organization_name(client):
    """PUT creates the profile and writes organization_name through; GET reflects both."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner3@example.com")
    h = _auth_header(owner["access_token"])

    create_resp = await client.put(
        BUSINESS_DNA,
        json={
            "organization_name": "Acme Corp",
            "vision": "See far",
            "capital_investment_amount": "25000000.00",
        },
        headers=h,
    )
    assert create_resp.status_code == 200
    body = create_resp.json()
    assert body["organization_name"] == "Acme Corp"
    assert body["vision"] == "See far"
    assert body["capital_investment_amount"] == "25000000.00"
    assert body["core_values"] == []

    get_resp = await client.get(BUSINESS_DNA, headers=h)
    assert get_resp.status_code == 200
    assert get_resp.json()["organization_name"] == "Acme Corp"
    assert get_resp.json()["vision"] == "See far"


@pytest.mark.asyncio
async def test_partial_update_preserves_untouched_fields(client):
    """A second PUT with only one field set doesn't wipe fields set earlier."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner4@example.com")
    h = _auth_header(owner["access_token"])

    await client.put(BUSINESS_DNA, json={"vision": "See far", "mission": "Deliver value"}, headers=h)
    update_resp = await client.put(BUSINESS_DNA, json={"mission": "Deliver more value"}, headers=h)

    assert update_resp.status_code == 200
    assert update_resp.json()["vision"] == "See far"
    assert update_resp.json()["mission"] == "Deliver more value"


@pytest.mark.asyncio
async def test_capital_investment_amount_hidden_for_non_privileged_role(client, monkeypatch):
    """An employee never sees capital_investment_amount; HR Administrator does."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner5@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "dna_emp5@example.com", "employee")
    h_owner = _auth_header(owner["access_token"])
    h_employee = _auth_header(employee["access_token"])

    await client.put(BUSINESS_DNA, json={"capital_investment_amount": "10000000.00"}, headers=h_owner)

    owner_view = await client.get(BUSINESS_DNA, headers=h_owner)
    employee_view = await client.get(BUSINESS_DNA, headers=h_employee)

    assert owner_view.json()["capital_investment_amount"] == "10000000.00"
    assert employee_view.json()["capital_investment_amount"] is None


@pytest.mark.asyncio
async def test_capital_investment_amount_visible_for_business_executive(client, monkeypatch):
    """business_executive is the other role explicitly granted visibility."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner6@example.com")
    exec_member = await _invite_and_accept(
        client, monkeypatch, owner, "dna_exec6@example.com", "business_executive"
    )
    h_owner = _auth_header(owner["access_token"])

    await client.put(BUSINESS_DNA, json={"capital_investment_amount": "5000000.00"}, headers=h_owner)

    exec_view = await client.get(BUSINESS_DNA, headers=_auth_header(exec_member["access_token"]))
    assert exec_view.json()["capital_investment_amount"] == "5000000.00"


@pytest.mark.asyncio
async def test_core_value_create_list_update_delete(client):
    """Full CRUD lifecycle for a core value, nested under its Business DNA profile."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner7@example.com")
    h = _auth_header(owner["access_token"])

    await client.put(BUSINESS_DNA, json={"vision": "See far"}, headers=h)

    create_resp = await client.post(CORE_VALUES, json={"value": "Integrity"}, headers=h)
    assert create_resp.status_code == 200
    core_value_id = create_resp.json()["id"]

    list_resp = await client.get(CORE_VALUES, headers=h)
    assert [v["value"] for v in list_resp.json()] == ["Integrity"]

    update_resp = await client.patch(
        f"{CORE_VALUES}/{core_value_id}", json={"value": "Radical Integrity"}, headers=h
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["value"] == "Radical Integrity"

    delete_resp = await client.delete(f"{CORE_VALUES}/{core_value_id}", headers=h)
    assert delete_resp.status_code == 204

    final_list = await client.get(CORE_VALUES, headers=h)
    assert final_list.json() == []


@pytest.mark.asyncio
async def test_create_core_value_404s_without_a_business_dna_profile(client):
    """Adding a core value before any Business DNA profile exists 404s."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner8@example.com")
    resp = await client.post(
        CORE_VALUES, json={"value": "Integrity"}, headers=_auth_header(owner["access_token"])
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_core_value_mutations_require_hr_admin_role(client, monkeypatch):
    """An employee-role member is rejected with 403 when creating a core value."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_owner9@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "dna_emp9@example.com", "employee")
    await client.put(BUSINESS_DNA, json={"vision": "See far"}, headers=_auth_header(owner["access_token"]))

    resp = await client.post(
        CORE_VALUES, json={"value": "Integrity"}, headers=_auth_header(employee["access_token"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_nonexistent_core_value_404s(client):
    """PATCHing a core value id that doesn't exist 404s."""
    from tests.conftest import register_verified_and_login
    import uuid

    owner = await register_verified_and_login(client, email="dna_owner10@example.com")
    resp = await client.patch(
        f"{CORE_VALUES}/{uuid.uuid4()}",
        json={"value": "Anything"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 404
