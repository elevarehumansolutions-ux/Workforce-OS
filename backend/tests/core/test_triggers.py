"""trigger_ai_suggestion_generation: the debounced, enqueue-by-name trigger.

Scenario: Adaeze toggles Operations' Critical flag on, off, then on again,
three real saves in a few seconds. Only the first should enqueue a run —
the other two are covered by the same 60-second window.

Uses the real dev Redis (already part of this stack), not a mock: SET NX EX
is the actual mechanism being tested. celery.send_task is faked, so nothing
is really published to the worker queue.
"""
import asyncio
import uuid

import pytest
import redis.asyncio as aioredis

from app.core import triggers
from app.core.config import settings
from app.core.task_names import AI_GENERATE_SUGGESTIONS_TASK


async def _clear(organization_id):
    client = aioredis.from_url(settings.redis_url)
    await client.delete(f"ai_suggestions:debounce:{organization_id}")
    await client.aclose()


def _fake_send_task(monkeypatch):
    sent = []
    monkeypatch.setattr(triggers.celery, "send_task", lambda name, args: sent.append((name, args)))
    return sent


@pytest.mark.asyncio
async def test_the_first_trigger_enqueues_the_right_task_with_the_org_id(monkeypatch):
    """One toggle: the task is sent by name, with the organization id as a string."""
    org_id = uuid.uuid4()
    await _clear(org_id)
    sent = _fake_send_task(monkeypatch)

    enqueued = await triggers.trigger_ai_suggestion_generation(org_id, ttl_seconds=5)

    assert enqueued is True
    assert sent == [(AI_GENERATE_SUGGESTIONS_TASK, [str(org_id)])]
    await _clear(org_id)


@pytest.mark.asyncio
async def test_a_second_trigger_within_the_window_is_a_quiet_no_op(monkeypatch):
    """Three real toggles in a few seconds; only the first should enqueue."""
    org_id = uuid.uuid4()
    await _clear(org_id)
    sent = _fake_send_task(monkeypatch)

    first = await triggers.trigger_ai_suggestion_generation(org_id, ttl_seconds=5)
    second = await triggers.trigger_ai_suggestion_generation(org_id, ttl_seconds=5)
    third = await triggers.trigger_ai_suggestion_generation(org_id, ttl_seconds=5)

    assert (first, second, third) == (True, False, False)
    assert len(sent) == 1
    await _clear(org_id)


@pytest.mark.asyncio
async def test_another_organizations_debounce_window_is_independent(monkeypatch):
    """Org A's cooldown must not block org B's own trigger."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    await _clear(org_a)
    await _clear(org_b)
    sent = _fake_send_task(monkeypatch)

    a_result = await triggers.trigger_ai_suggestion_generation(org_a, ttl_seconds=5)
    b_result = await triggers.trigger_ai_suggestion_generation(org_b, ttl_seconds=5)

    assert (a_result, b_result) == (True, True)
    assert {name for name, _ in sent} == {AI_GENERATE_SUGGESTIONS_TASK}
    await _clear(org_a)
    await _clear(org_b)


@pytest.mark.asyncio
async def test_the_window_expiring_allows_a_new_trigger(monkeypatch):
    """After the cooldown passes, the same organization can trigger again."""
    org_id = uuid.uuid4()
    await _clear(org_id)
    sent = _fake_send_task(monkeypatch)

    first = await triggers.trigger_ai_suggestion_generation(org_id, ttl_seconds=1)
    await asyncio.sleep(1.2)
    second = await triggers.trigger_ai_suggestion_generation(org_id, ttl_seconds=1)

    assert (first, second) == (True, True)
    assert len(sent) == 2
    await _clear(org_id)
