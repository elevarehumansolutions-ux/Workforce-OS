"""HTTP-level tests for /kpis, /departments/{id}/kpis, and /kpis/{id}/scores."""
import uuid
from datetime import date, timedelta

import pytest

from tests.conftest import register_verified_and_login

KPIS = "/api/v1/kpis"
DEPARTMENTS = "/api/v1/departments"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _invite_and_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    from unittest.mock import MagicMock
    import app.modules.tenancy_identity.router as membership_router_module

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        "/api/v1/memberships",
        json={"email": email, "role": role},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Test Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return accept_resp.json()


async def _make_department(client, headers, name="Sales") -> str:
    resp = await client.post(DEPARTMENTS, json={"name": name}, headers=headers)
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Single-KPI CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kpis_require_authentication(client):
    """GET /kpis rejects an unauthenticated request with 401."""
    resp = await client.get(KPIS)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_kpi_requires_hr_admin_role(client, monkeypatch):
    """A manager-role member is rejected with 403 when creating a KPI."""
    owner = await register_verified_and_login(client, email="kpi_owner1@example.com")
    manager = await _invite_and_accept(client, monkeypatch, owner, "kpi_mgr1@example.com", "manager")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    resp = await client.post(
        KPIS,
        json={"department_id": dept_id, "name": "Deals closed", "weight": 30},
        headers=_auth_header(manager["access_token"]),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_any_role_can_read_kpis(client, monkeypatch):
    """An employee-role member can still list KPIs, unlike creating them."""
    owner = await register_verified_and_login(client, email="kpi_owner2@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "kpi_emp2@example.com", "employee")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    await client.post(KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 30}, headers=h)
    resp = await client.get(KPIS, headers=_auth_header(employee["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_create_kpi_defaults_tracking_mode_manual_and_is_inverse_false(client):
    """Creating a KPI with no tracking_mode/is_inverse gets sane defaults."""
    owner = await register_verified_and_login(client, email="kpi_owner3@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    resp = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 30}, headers=h
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tracking_mode"] == "manual"
    assert body["is_inverse"] is False


@pytest.mark.asyncio
async def test_create_kpi_rejects_weight_exceeding_group_total(client):
    """Adding a KPI that would push the group over 100% is rejected with 409."""
    owner = await register_verified_and_login(client, email="kpi_owner4@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    await client.post(KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 60}, headers=h)
    resp = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Pipeline value", "weight": 50}, headers=h
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "KPI_WEIGHT_MISMATCH"
    assert "110" in resp.json()["message"]


@pytest.mark.asyncio
async def test_update_kpi_partial_update_preserves_untouched_fields(client):
    """PATCH with one field set doesn't wipe fields set earlier."""
    owner = await register_verified_and_login(client, email="kpi_owner5@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    created = await client.post(
        KPIS,
        json={"department_id": dept_id, "name": "Deals closed", "weight": 30, "unit": "deals"},
        headers=h,
    )
    kpi_id = created.json()["id"]

    resp = await client.patch(f"{KPIS}/{kpi_id}", json={"weight": 40}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Deals closed"
    assert resp.json()["unit"] == "deals"
    assert resp.json()["weight"] == "40.00"


@pytest.mark.asyncio
async def test_update_kpi_rejects_weight_exceeding_group_total(client):
    """Editing a KPI's weight over the group's remaining room is rejected with 409."""
    owner = await register_verified_and_login(client, email="kpi_owner6@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    k1 = await client.post(KPIS, json={"department_id": dept_id, "name": "A", "weight": 30}, headers=h)
    await client.post(KPIS, json={"department_id": dept_id, "name": "B", "weight": 60}, headers=h)

    resp = await client.patch(f"{KPIS}/{k1.json()['id']}", json={"weight": 50}, headers=h)
    assert resp.status_code == 409
    assert "110" in resp.json()["message"]


@pytest.mark.asyncio
async def test_get_nonexistent_kpi_404s(client):
    """GETting an id that doesn't exist 404s."""
    owner = await register_verified_and_login(client, email="kpi_owner7@example.com")
    resp = await client.get(f"{KPIS}/{uuid.uuid4()}", headers=_auth_header(owner["access_token"]))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_kpis_filters_by_department_id(client):
    """?department_id= restricts the list to that department's KPIs."""
    owner = await register_verified_and_login(client, email="kpi_owner8@example.com")
    h = _auth_header(owner["access_token"])
    dept_a = await _make_department(client, h, "Sales")
    dept_b = await _make_department(client, h, "Ops")

    await client.post(KPIS, json={"department_id": dept_a, "name": "Sales KPI", "weight": 100}, headers=h)
    await client.post(KPIS, json={"department_id": dept_b, "name": "Ops KPI", "weight": 100}, headers=h)

    resp = await client.get(KPIS, params={"department_id": dept_a}, headers=h)
    assert resp.status_code == 200
    assert [k["name"] for k in resp.json()["data"]] == ["Sales KPI"]


@pytest.mark.asyncio
async def test_list_kpis_is_org_scoped(client):
    """RLS proof: an org only ever sees its own KPIs."""
    owner_a = await register_verified_and_login(client, email="kpi_owner_a@example.com")
    owner_b = await register_verified_and_login(client, email="kpi_owner_b@example.com")
    h_a = _auth_header(owner_a["access_token"])
    h_b = _auth_header(owner_b["access_token"])

    dept_a = await _make_department(client, h_a)
    dept_b = await _make_department(client, h_b)
    await client.post(KPIS, json={"department_id": dept_a, "name": "A's KPI", "weight": 100}, headers=h_a)
    await client.post(KPIS, json={"department_id": dept_b, "name": "B's KPI", "weight": 100}, headers=h_b)

    resp_a = await client.get(KPIS, headers=h_a)
    assert resp_a.json()["pagination"]["total"] == 1
    assert resp_a.json()["data"][0]["name"] == "A's KPI"


# ---------------------------------------------------------------------------
# Group reconcile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconcile_kpis_rejects_total_not_equal_100(client):
    """PUT .../kpis rejects a submitted list that doesn't sum to exactly 100."""
    owner = await register_verified_and_login(client, email="kpi_owner9@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    resp = await client.put(
        f"{DEPARTMENTS}/{dept_id}/kpis",
        json={"kpis": [{"name": "A", "weight": 30}, {"name": "B", "weight": 60}]},
        headers=h,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "KPI_WEIGHT_MISMATCH"
    assert "90" in resp.json()["message"]


@pytest.mark.asyncio
async def test_reconcile_kpis_creates_updates_and_deletes_in_one_call(client):
    """The group save handles create+update+delete atomically, in one request."""
    owner = await register_verified_and_login(client, email="kpi_owner10@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    a = await client.post(KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 30}, headers=h)
    b = await client.post(KPIS, json={"department_id": dept_id, "name": "Pipeline value", "weight": 70}, headers=h)
    a_id = a.json()["id"]

    resp = await client.put(
        f"{DEPARTMENTS}/{dept_id}/kpis",
        json={
            "kpis": [
                {"id": a_id, "name": "Deals closed", "weight": 40},
                {"name": "Customer satisfaction", "weight": 60},
            ]
        },
        headers=h,
    )
    assert resp.status_code == 200
    names_and_weights = {(k["name"], k["weight"]) for k in resp.json()["kpis"]}
    assert names_and_weights == {("Deals closed", "40.00"), ("Customer satisfaction", "60.00")}

    # Pipeline value is gone — no standalone DELETE, it's just missing from the list
    get_b = await client.get(f"{KPIS}/{b.json()['id']}", headers=h)
    assert get_b.status_code == 404


@pytest.mark.asyncio
async def test_reconcile_kpis_requires_hr_admin_role(client, monkeypatch):
    """A manager-role member is rejected with 403 on the group reconcile."""
    owner = await register_verified_and_login(client, email="kpi_owner11@example.com")
    manager = await _invite_and_accept(client, monkeypatch, owner, "kpi_mgr11@example.com", "manager")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)

    resp = await client.put(
        f"{DEPARTMENTS}/{dept_id}/kpis",
        json={"kpis": [{"name": "A", "weight": 100}]},
        headers=_auth_header(manager["access_token"]),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_business_executive_can_record_scores_but_not_create_kpis(client, monkeypatch):
    """Business Executive is one of the two score-write roles, unlike plain KPI mutations."""
    owner = await register_verified_and_login(client, email="kpi_owner12@example.com")
    exec_user = await _invite_and_accept(
        client, monkeypatch, owner, "kpi_exec12@example.com", "business_executive"
    )
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)
    kpi = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 100, "target_value": 20},
        headers=h,
    )
    kpi_id = kpi.json()["id"]

    exec_headers = _auth_header(exec_user["access_token"])
    today = date.today()
    score_resp = await client.post(
        f"{KPIS}/{kpi_id}/scores",
        json={
            "period_start": str(today - timedelta(days=45)),
            "period_end": str(today + timedelta(days=45)),
            "actual_value": 12,
        },
        headers=exec_headers,
    )
    assert score_resp.status_code == 200
    assert score_resp.json()["score_percentage"] == "60.00"

    create_resp = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Other", "weight": 1}, headers=exec_headers
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_upsert_score_updates_same_row_for_same_open_period(client):
    """Calling the scores endpoint twice for the same open period updates, not duplicates."""
    owner = await register_verified_and_login(client, email="kpi_owner13@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)
    kpi = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 100, "target_value": 20},
        headers=h,
    )
    kpi_id = kpi.json()["id"]
    today = date.today()
    period = {
        "period_start": str(today - timedelta(days=45)),
        "period_end": str(today + timedelta(days=45)),
    }

    first = await client.post(f"{KPIS}/{kpi_id}/scores", json={**period, "actual_value": 8}, headers=h)
    second = await client.post(f"{KPIS}/{kpi_id}/scores", json={**period, "actual_value": 14}, headers=h)
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["actual_value"] == "14.00"
    assert second.json()["score_percentage"] == "70.00"

    history = await client.get(f"{KPIS}/{kpi_id}/scores", headers=h)
    assert history.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_upsert_score_rejects_closed_period(client):
    """A score for a period whose period_end has already passed is rejected with 409."""
    owner = await register_verified_and_login(client, email="kpi_owner14@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)
    kpi = await client.post(
        KPIS, json={"department_id": dept_id, "name": "Deals closed", "weight": 100}, headers=h
    )
    kpi_id = kpi.json()["id"]
    today = date.today()

    resp = await client.post(
        f"{KPIS}/{kpi_id}/scores",
        json={
            "period_start": str(today - timedelta(days=100)),
            "period_end": str(today - timedelta(days=10)),
            "actual_value": 5,
        },
        headers=h,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "KPI_SCORE_PERIOD_CLOSED"


@pytest.mark.asyncio
async def test_score_percentage_honors_is_inverse(client):
    """An inverse KPI's score_percentage uses target/actual, not actual/target."""
    owner = await register_verified_and_login(client, email="kpi_owner15@example.com")
    h = _auth_header(owner["access_token"])
    dept_id = await _make_department(client, h)
    kpi = await client.post(
        KPIS,
        json={
            "department_id": dept_id, "name": "Customer complaints", "weight": 100,
            "target_value": 10, "is_inverse": True,
        },
        headers=h,
    )
    kpi_id = kpi.json()["id"]
    today = date.today()

    resp = await client.post(
        f"{KPIS}/{kpi_id}/scores",
        json={
            "period_start": str(today - timedelta(days=1)),
            "period_end": str(today + timedelta(days=1)),
            "actual_value": 6,
        },
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["score_percentage"] == "166.67" or resp.json()["score_percentage"].startswith("166.6")
