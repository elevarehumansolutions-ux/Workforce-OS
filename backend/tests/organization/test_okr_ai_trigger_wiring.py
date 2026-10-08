"""Which OKR writes fire the AI generation trigger.

Scenario: Adaeze saves a new objective. That's one of the two documented
generation triggers (missing_department reads OKRs as prompt context, so a
fresh objective can surface a gap). Editing an existing OKR's title is not
the same event, so it shouldn't fire anything — proven by replacing the
trigger with a recorder, so no real Redis or Celery call happens.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login
import app.modules.okrs.router as okrs_router

OKRS = "/api/v1/okrs"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _fake_trigger(monkeypatch):
    calls = []

    async def fake(organization_id, **kwargs):
        calls.append(organization_id)
        return True

    monkeypatch.setattr(okrs_router, "trigger_ai_suggestion_generation", fake)
    return calls


@pytest.mark.asyncio
async def test_creating_an_objective_fires_the_trigger(client, monkeypatch):
    """A new objective is one of the two documented generation triggers."""
    owner = await register_verified_and_login(client, email="okr_trig1@example.com")
    h = _auth_header(owner["access_token"])
    calls = _fake_trigger(monkeypatch)

    resp = await client.post(OKRS, json={"title": "Cut late deliveries by 20%"}, headers=h)

    assert resp.status_code == 200
    assert calls == [uuid.UUID(owner["organization"]["id"])]


@pytest.mark.asyncio
async def test_editing_an_existing_objective_does_not_fire_it(client, monkeypatch):
    """A retitle isn't 'a new objective saved' — the documented trigger event."""
    owner = await register_verified_and_login(client, email="okr_trig2@example.com")
    h = _auth_header(owner["access_token"])
    okr = await client.post(OKRS, json={"title": "Cut late deliveries by 20%"}, headers=h)
    calls = _fake_trigger(monkeypatch)

    resp = await client.patch(
        f"{OKRS}/{okr.json()['id']}", json={"title": "Cut late deliveries by 25%"}, headers=h
    )

    assert resp.status_code == 200
    assert calls == []
