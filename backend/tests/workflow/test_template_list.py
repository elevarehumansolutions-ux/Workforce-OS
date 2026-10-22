"""Tests for GET /workflow-templates (M11 slice B, endpoint 2)."""
import pytest

from tests.tasks.test_tasks_router import _world
from tests.workflow.test_template_create import TEMPLATES


async def _create(client, headers, name: str, department_id: str) -> dict:
    """Create a template through the API and return its JSON."""
    response = await client.post(
        TEMPLATES, json={"name": name, "department_id": department_id}, headers=headers
    )
    assert response.status_code == 200
    return response.json()


def _names(response) -> list[str]:
    return [t["name"] for t in response.json()["data"]]


@pytest.mark.asyncio
async def test_any_member_lists_templates_by_name_and_sees_only_their_own_company(client, monkeypatch):
    """An employee can read; the list is alphabetical; another company's templates never appear."""
    w = await _world(client, monkeypatch, "tl1")
    other = await _world(client, monkeypatch, "tl2")
    await _create(client, w.hr, "Refund Request", w.sales)
    await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _create(client, other.hr, "Someone Else's Process", other.dispatch)

    listed = await client.get(TEMPLATES, headers=w.chidi.h)

    assert listed.status_code == 200
    assert _names(listed) == ["Client Onboarding", "Refund Request"]
    assert listed.json()["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_the_list_can_be_filtered_by_owning_department(client, monkeypatch):
    """department_id narrows the list to the templates that department owns."""
    w = await _world(client, monkeypatch, "tl3")
    await _create(client, w.hr, "Client Onboarding", w.dispatch)
    await _create(client, w.hr, "Refund Request", w.sales)

    listed = await client.get(TEMPLATES, params={"department_id": w.sales}, headers=w.hr)

    assert _names(listed) == ["Refund Request"]


@pytest.mark.asyncio
async def test_the_list_is_paginated(client, monkeypatch):
    """Three templates, two per page: the second page holds the last one."""
    w = await _world(client, monkeypatch, "tl4")
    for name in ("Alpha", "Bravo", "Charlie"):
        await _create(client, w.hr, name, w.dispatch)

    first = await client.get(TEMPLATES, params={"limit": 2}, headers=w.hr)
    second = await client.get(TEMPLATES, params={"limit": 2, "page": 2}, headers=w.hr)
    bad_page = await client.get(TEMPLATES, params={"page": 0}, headers=w.hr)

    assert _names(first) == ["Alpha", "Bravo"]
    assert _names(second) == ["Charlie"]
    assert first.json()["pagination"]["total"] == 3
    assert bad_page.status_code == 422
