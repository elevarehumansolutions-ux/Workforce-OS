"""Regression test: PUT /business-dna must not read tenant data after commit().

In production every ``commit()`` ends the transaction, and the tenant context
(``set_config('app.current_org_id', ..., true)``) is transaction-local, so it is
gone afterwards. Reads issued after the commit run with no tenant context and
row-level security hides every row. The test session normally lives inside one
outer transaction, where ``commit()`` never ends anything and the setting
survives, so this bug was invisible to the rest of the suite.
"""
import pytest
from sqlalchemy import text

BUSINESS_DNA = "/api/v1/business-dna"
CORE_VALUES = "/api/v1/business-dna/core-values"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _commit_like_production(db_session, monkeypatch) -> None:
    """Make ``commit()`` also drop the transaction-local tenant context.

    Clears ``app.current_user_id`` too: login sets it earlier in the shared
    test transaction, but a real request to this endpoint never has it, and
    ``organizations``' policy would otherwise fall back to it.
    """
    original_commit = db_session.commit

    async def commit_and_forget_tenant_context():
        await original_commit()
        for setting in ("app.current_org_id", "app.current_user_id"):
            await db_session.execute(
                text("SELECT set_config(:name, '', true)"), {"name": setting}
            )

    monkeypatch.setattr(db_session, "commit", commit_and_forget_tenant_context)


@pytest.mark.asyncio
async def test_upsert_response_is_built_with_tenant_context_after_commit(
    client, db_session, monkeypatch
):
    """PUT returns 200 with the org name and core values even when commit() clears tenant context."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="dna_ctx_owner@example.com")
    headers = _auth_header(owner["access_token"])

    first = await client.put(BUSINESS_DNA, json={"vision": "See far"}, headers=headers)
    assert first.status_code == 200
    value_resp = await client.post(CORE_VALUES, json={"value": "Integrity"}, headers=headers)
    assert value_resp.status_code == 200

    _commit_like_production(db_session, monkeypatch)

    resp = await client.put(
        BUSINESS_DNA,
        json={"organization_name": "Acme Corp", "timezone": "Africa/Lagos", "mission": "Ship it"},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["organization_name"] == "Acme Corp"
    assert body["timezone"] == "Africa/Lagos"
    assert body["mission"] == "Ship it"
    assert body["vision"] == "See far"
    assert [v["value"] for v in body["core_values"]] == ["Integrity"]
