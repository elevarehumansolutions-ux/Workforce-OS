"""HTTP-level tests for per-organization department-name uniqueness.

Names are unique among an organization's non-deleted departments, compared
on a normalized key (case, spacing and Unicode variants count as the same
name). Enforced by a partial unique index, surfaced as a 409 on create and
on rename (08_DECISIONS.md 2026-09-24).
"""
import pytest

DEPARTMENTS = "/api/v1/departments"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _owner(client, email):
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email=email)
    return _auth_header(owner["access_token"])


@pytest.mark.asyncio
async def test_duplicate_department_name_is_a_conflict(client):
    """Creating a second department with the same name in one org is a 409 naming it."""
    h = await _owner(client, "dept_uniq1@example.com")
    assert (await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)).status_code == 200

    resp = await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)

    assert resp.status_code == 409
    assert "Operations" in resp.json()["message"]


@pytest.mark.asyncio
async def test_case_spacing_and_unicode_variants_are_the_same_name(client):
    """Formatting variants of an existing name don't get around the rule."""
    h = await _owner(client, "dept_uniq2@example.com")
    await client.post(DEPARTMENTS, json={"name": "Customer Success"}, headers=h)

    for variant in ["customer success", "  Customer   SUCCESS ", "Customer\u00a0Success"]:
        resp = await client.post(DEPARTMENTS, json={"name": variant}, headers=h)
        assert resp.status_code == 409, variant

    # A genuinely different name is fine — normalization handles formatting, not synonyms.
    assert (await client.post(DEPARTMENTS, json={"name": "Customer Success Team"}, headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_the_session_stays_usable_after_a_rejected_create(client):
    """The SAVEPOINT means a rejected insert doesn't poison the rest of the request's transaction."""
    h = await _owner(client, "dept_uniq3@example.com")
    await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)
    assert (await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)).status_code == 409

    ok = await client.post(DEPARTMENTS, json={"name": "Finance"}, headers=h)
    assert ok.status_code == 200
    listed = await client.get(DEPARTMENTS, headers=h)
    assert {d["name"] for d in listed.json()["data"]} == {"Operations", "Finance"}


@pytest.mark.asyncio
async def test_two_organizations_can_each_have_the_same_department_name(client):
    """Uniqueness is per organization — one tenant's names never block another's."""
    h_a = await _owner(client, "dept_uniq4a@example.com")
    h_b = await _owner(client, "dept_uniq4b@example.com")

    assert (await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h_a)).status_code == 200
    assert (await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h_b)).status_code == 200


@pytest.mark.asyncio
async def test_a_deleted_departments_name_can_be_reused(client):
    """The uniqueness rule only covers non-deleted departments."""
    h = await _owner(client, "dept_uniq5@example.com")
    first = await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)
    assert (await client.delete(f"{DEPARTMENTS}/{first.json()['id']}", headers=h)).status_code == 200

    again = await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)

    assert again.status_code == 200
    assert again.json()["id"] != first.json()["id"]


@pytest.mark.asyncio
async def test_renaming_to_an_existing_name_is_a_conflict_and_changes_nothing(client):
    """A rename that would duplicate another department is a 409, and the name is unchanged."""
    h = await _owner(client, "dept_uniq6@example.com")
    await client.post(DEPARTMENTS, json={"name": "Operations"}, headers=h)
    finance = await client.post(DEPARTMENTS, json={"name": "Finance"}, headers=h)
    finance_id = finance.json()["id"]

    resp = await client.patch(f"{DEPARTMENTS}/{finance_id}", json={"name": "  operations "}, headers=h)

    assert resp.status_code == 409
    assert (await client.get(f"{DEPARTMENTS}/{finance_id}", headers=h)).json()["name"] == "Finance"


@pytest.mark.asyncio
async def test_a_department_can_be_renamed_to_a_variant_of_its_own_name(client):
    """Fixing the capitalization of your own name isn't a conflict with yourself."""
    h = await _owner(client, "dept_uniq7@example.com")
    dept = await client.post(DEPARTMENTS, json={"name": "operations"}, headers=h)

    resp = await client.patch(f"{DEPARTMENTS}/{dept.json()['id']}", json={"name": "Operations"}, headers=h)

    assert resp.status_code == 200
    assert resp.json()["name"] == "Operations"
