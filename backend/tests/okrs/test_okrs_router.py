"""HTTP-level tests for /okrs and /okrs/{id}/key-results."""
import uuid

import pytest

OKRS = "/api/v1/okrs"
KEY_RESULTS = "/api/v1/key-results"
DEPARTMENTS = "/api/v1/departments"
LOCATIONS = "/api/v1/locations"
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


# ---------------------------------------------------------------------------
# OKRs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_okrs_require_authentication(client):
    """GET /okrs rejects an unauthenticated request with 401."""
    resp = await client.get(OKRS)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_okr_requires_hr_admin_role(client, monkeypatch):
    """A manager-role member is rejected with 403 when creating an OKR."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner1@example.com")
    manager = await _invite_and_accept(client, monkeypatch, owner, "okr_mgr1@example.com", "manager")

    resp = await client.post(
        OKRS, json={"title": "Grow revenue"}, headers=_auth_header(manager["access_token"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_any_role_can_read_okrs(client, monkeypatch):
    """An employee-role member can still successfully list OKRs, unlike creating them."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner2@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "okr_emp2@example.com", "employee")

    await client.post(OKRS, json={"title": "Grow revenue"}, headers=_auth_header(owner["access_token"]))
    resp = await client.get(OKRS, headers=_auth_header(employee["access_token"]))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_corporate_okr_has_null_department_and_location(client):
    """Omitting department_id/location_id creates a corporate, org-wide OKR."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner3@example.com")
    h = _auth_header(owner["access_token"])

    resp = await client.post(OKRS, json={"title": "Grow revenue 20%"}, headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Grow revenue 20%"
    assert body["department_id"] is None
    assert body["location_id"] is None


@pytest.mark.asyncio
async def test_create_departmental_okr_scoped_to_department(client):
    """Setting department_id creates a departmental OKR scoped to it."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner4@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    department_id = dept.json()["id"]

    resp = await client.post(
        OKRS, json={"title": "Close more deals", "department_id": department_id}, headers=h
    )
    assert resp.status_code == 200
    assert resp.json()["department_id"] == department_id
    assert resp.json()["location_id"] is None


@pytest.mark.asyncio
async def test_update_okr_partial_update_preserves_untouched_fields(client):
    """PATCH with one field set doesn't wipe fields set earlier."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner5@example.com")
    h = _auth_header(owner["access_token"])

    create_resp = await client.post(OKRS, json={"title": "Grow revenue"}, headers=h)
    okr_id = create_resp.json()["id"]

    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    update_resp = await client.patch(
        f"{OKRS}/{okr_id}", json={"department_id": dept.json()["id"]}, headers=h
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Grow revenue"
    assert update_resp.json()["department_id"] == dept.json()["id"]


@pytest.mark.asyncio
async def test_get_nonexistent_okr_404s(client):
    """GETting an id that doesn't exist 404s."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner6@example.com")
    resp = await client.get(f"{OKRS}/{uuid.uuid4()}", headers=_auth_header(owner["access_token"]))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_nonexistent_okr_404s(client):
    """PATCHing an id that doesn't exist 404s."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner7@example.com")
    resp = await client.patch(
        f"{OKRS}/{uuid.uuid4()}", json={"title": "Anything"}, headers=_auth_header(owner["access_token"])
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_okrs_filters_by_department_id(client):
    """?department_id= restricts the list to that department's OKRs."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner8@example.com")
    h = _auth_header(owner["access_token"])

    dept_a = await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=h)
    dept_b = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    dept_a_id, dept_b_id = dept_a.json()["id"], dept_b.json()["id"]

    await client.post(OKRS, json={"title": "Corporate goal"}, headers=h)
    await client.post(OKRS, json={"title": "Sales goal", "department_id": dept_a_id}, headers=h)
    await client.post(OKRS, json={"title": "Ops goal", "department_id": dept_b_id}, headers=h)

    resp = await client.get(OKRS, params={"department_id": dept_a_id}, headers=h)
    assert resp.status_code == 200
    assert [o["title"] for o in resp.json()["data"]] == ["Sales goal"]


@pytest.mark.asyncio
async def test_list_okrs_filters_by_location_id(client):
    """?location_id= restricts the list to that location's OKRs."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner9@example.com")
    h = _auth_header(owner["access_token"])

    loc_a = await client.post(LOCATIONS, json={"name": "Lagos"}, headers=h)
    loc_b = await client.post(LOCATIONS, json={"name": "Abuja"}, headers=h)
    loc_a_id, loc_b_id = loc_a.json()["id"], loc_b.json()["id"]

    await client.post(OKRS, json={"title": "Org-wide goal"}, headers=h)
    await client.post(OKRS, json={"title": "Lagos goal", "location_id": loc_a_id}, headers=h)
    await client.post(OKRS, json={"title": "Abuja goal", "location_id": loc_b_id}, headers=h)

    resp = await client.get(OKRS, params={"location_id": loc_a_id}, headers=h)
    assert resp.status_code == 200
    assert [o["title"] for o in resp.json()["data"]] == ["Lagos goal"]


@pytest.mark.asyncio
async def test_list_okrs_is_paginated_and_org_scoped(client):
    """Listing OKRs is paginated and scoped to the caller's own org.

    RLS proof: an org only ever sees its own OKRs, even though both orgs'
    rows sit in the same table.
    """
    from tests.conftest import register_verified_and_login

    owner_a = await register_verified_and_login(client, email="okr_owner_a@example.com")
    owner_b = await register_verified_and_login(client, email="okr_owner_b@example.com")

    for title in ("Goal 1", "Goal 2", "Goal 3"):
        resp = await client.post(OKRS, json={"title": title}, headers=_auth_header(owner_a["access_token"]))
        assert resp.status_code == 200
    await client.post(OKRS, json={"title": "Other org's goal"}, headers=_auth_header(owner_b["access_token"]))

    page1 = await client.get(OKRS, params={"limit": 2}, headers=_auth_header(owner_a["access_token"]))
    assert page1.status_code == 200
    assert page1.json()["pagination"]["total"] == 3
    assert len(page1.json()["data"]) == 2

    resp_b = await client.get(OKRS, headers=_auth_header(owner_b["access_token"]))
    assert resp_b.json()["pagination"]["total"] == 1
    assert resp_b.json()["data"][0]["title"] == "Other org's goal"


@pytest.mark.asyncio
async def test_creating_a_new_okr_does_not_touch_existing_ones(client):
    """Adding an objective is additive — existing OKRs are untouched (08_DECISIONS.md 2026-09-02)."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="okr_owner10@example.com")
    h = _auth_header(owner["access_token"])

    first = await client.post(OKRS, json={"title": "First goal"}, headers=h)
    first_id = first.json()["id"]
    await client.post(OKRS, json={"title": "Second goal"}, headers=h)

    get_first_again = await client.get(f"{OKRS}/{first_id}", headers=h)
    assert get_first_again.json()["title"] == "First goal"

    list_resp = await client.get(OKRS, headers=h)
    assert list_resp.json()["pagination"]["total"] == 2


# ---------------------------------------------------------------------------
# Key results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_key_result_requires_hr_admin_role(client, monkeypatch):
    """A manager-role member is rejected with 403 when adding a key result."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="kr_owner1@example.com")
    manager = await _invite_and_accept(client, monkeypatch, owner, "kr_mgr1@example.com", "manager")

    okr = await client.post(OKRS, json={"title": "Grow revenue"}, headers=_auth_header(owner["access_token"]))
    okr_id = okr.json()["id"]

    resp = await client.post(
        f"{OKRS}/{okr_id}/key-results",
        json={"description": "Close 10 deals"},
        headers=_auth_header(manager["access_token"]),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_key_result_404s_for_nonexistent_okr(client):
    """Adding a key result under an OKR id that doesn't exist 404s."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="kr_owner2@example.com")
    resp = await client.post(
        f"{OKRS}/{uuid.uuid4()}/key-results",
        json={"description": "Close 10 deals"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_key_results_404s_for_nonexistent_okr(client):
    """Listing key results under an OKR id that doesn't exist 404s."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="kr_owner3@example.com")
    resp = await client.get(
        f"{OKRS}/{uuid.uuid4()}/key-results", headers=_auth_header(owner["access_token"])
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_key_result_create_list_update_lifecycle(client):
    """Full create/list/update lifecycle for a key result, nested under its OKR."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="kr_owner4@example.com")
    h = _auth_header(owner["access_token"])

    okr = await client.post(OKRS, json={"title": "Grow revenue"}, headers=h)
    okr_id = okr.json()["id"]

    create_resp = await client.post(
        f"{OKRS}/{okr_id}/key-results",
        json={"description": "Close 10 deals", "target_date": "2026-12-31"},
        headers=h,
    )
    assert create_resp.status_code == 200
    key_result_id = create_resp.json()["id"]
    assert create_resp.json()["okr_id"] == okr_id
    assert create_resp.json()["target_date"] == "2026-12-31"

    list_resp = await client.get(f"{OKRS}/{okr_id}/key-results", headers=h)
    assert list_resp.status_code == 200
    assert list_resp.json()["pagination"]["total"] == 1
    assert list_resp.json()["data"][0]["description"] == "Close 10 deals"

    update_resp = await client.patch(
        f"{KEY_RESULTS}/{key_result_id}", json={"description": "Close 15 deals"}, headers=h
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "Close 15 deals"
    assert update_resp.json()["target_date"] == "2026-12-31"  # untouched field survives


@pytest.mark.asyncio
async def test_update_nonexistent_key_result_404s(client):
    """PATCHing a key result id that doesn't exist 404s."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="kr_owner5@example.com")
    resp = await client.patch(
        f"{KEY_RESULTS}/{uuid.uuid4()}",
        json={"description": "Anything"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_okr_and_its_key_results_are_invisible_across_orgs(client):
    """An OKR (and its key results) created in org A is unreachable from org B — RLS proof."""
    from tests.conftest import register_verified_and_login

    owner_a = await register_verified_and_login(client, email="kr_owner_a@example.com")
    owner_b = await register_verified_and_login(client, email="kr_owner_b@example.com")

    okr = await client.post(
        OKRS, json={"title": "Org A's goal"}, headers=_auth_header(owner_a["access_token"])
    )
    okr_id = okr.json()["id"]
    await client.post(
        f"{OKRS}/{okr_id}/key-results",
        json={"description": "Org A's key result"},
        headers=_auth_header(owner_a["access_token"]),
    )

    b_header = _auth_header(owner_b["access_token"])
    assert (await client.get(f"{OKRS}/{okr_id}", headers=b_header)).status_code == 404
    assert (await client.get(f"{OKRS}/{okr_id}/key-results", headers=b_header)).status_code == 404
