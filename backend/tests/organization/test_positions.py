"""HTTP-level tests for /positions CRUD and the delete-blocked-while-
referenced rule (two independent reasons)."""
import pytest

DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_create_position_with_risk_and_criticality(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="pos_owner1@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    resp = await client.post(
        POSITIONS,
        json={
            "department_id": dept.json()["id"],
            "title": "General Manager",
            "is_critical": True,
            "risk_level": "high",
            "criticality_type": "revenue_generating",
        },
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] == "high"
    assert body["criticality_type"] == "revenue_generating"

    # Newly created position with neither field set stays genuinely NULL —
    # AI Suggestions (M7) fills these in later, a Position must be
    # creatable before they're known.
    resp2 = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "Clerk"}, headers=h)
    assert resp2.json()["risk_level"] is None
    assert resp2.json()["criticality_type"] is None


@pytest.mark.asyncio
async def test_position_self_referential_reporting_chain(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="pos_owner2@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    gm = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "GM"}, headers=h)
    assoc = await client.post(
        POSITIONS,
        json={
            "department_id": dept.json()["id"],
            "title": "Associate",
            "reports_to_position_id": gm.json()["id"],
        },
        headers=h,
    )
    assert assoc.status_code == 200
    assert assoc.json()["reports_to_position_id"] == gm.json()["id"]


@pytest.mark.asyncio
async def test_delete_position_blocked_by_both_reasons_at_once(client):
    from tests.conftest import register_verified_and_login
    from datetime import date

    owner = await register_verified_and_login(client, email="pos_owner3@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    gm = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "GM"}, headers=h)
    gm_id = gm.json()["id"]

    await client.post(
        POSITIONS,
        json={"department_id": dept.json()["id"], "title": "Associate", "reports_to_position_id": gm_id},
        headers=h,
    )
    await client.post(
        EMPLOYEES,
        json={
            "position_id": gm_id,
            "first_name": "Gina",
            "last_name": "Manager",
            "work_email": "gina@example.com",
            "start_date": date.today().isoformat(),
        },
        headers=h,
    )

    resp = await client.delete(f"{POSITIONS}/{gm_id}", headers=h)
    assert resp.status_code == 409
    message = resp.json()["message"]
    assert "active employee" in message
    assert "reporting to it" in message


@pytest.mark.asyncio
async def test_delete_position_succeeds_when_unreferenced(client):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="pos_owner4@example.com")
    h = _auth_header(owner["access_token"])

    dept = await client.post(DEPARTMENTS, json={"name": "Ops"}, headers=h)
    pos = await client.post(POSITIONS, json={"department_id": dept.json()["id"], "title": "Temp Role"}, headers=h)

    resp = await client.delete(f"{POSITIONS}/{pos.json()['id']}", headers=h)
    assert resp.status_code == 200

    get_after = await client.get(f"{POSITIONS}/{pos.json()['id']}", headers=h)
    assert get_after.status_code == 404
