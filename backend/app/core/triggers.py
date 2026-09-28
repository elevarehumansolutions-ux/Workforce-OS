"""Debounced, enqueue-by-name triggers for cross-module background jobs.

Scenario: Adaeze toggles Operations' Critical flag on, then off, then back
on, three real saves within a few seconds. Each save is a genuine change
worth reacting to, but firing three LLM calls for something one person did
in five seconds is wasted spend, not three genuine requests. A short,
per-organization Redis cooldown collapses them into one — the *first*
toggle enqueues a run; the next two, within the cooldown window, are quiet
no-ops (08_DECISIONS.md 2026-09-05, 2026-09-25).
"""

import logging
import uuid

import redis.asyncio as aioredis

from app.core.celery_app import celery
from app.core.config import settings
from app.core.task_names import AI_GENERATE_SUGGESTIONS_TASK

logger = logging.getLogger(__name__)

_DEBOUNCE_TTL_SECONDS = 60


async def trigger_ai_suggestion_generation(
    organization_id: uuid.UUID, *, ttl_seconds: int = _DEBOUNCE_TTL_SECONDS
) -> bool:
    """Ask the AI Suggestions engine to (re)generate for one organization.

    Callers: Org Structure's and OKR's services, after a change that could
    make a new suggestion true — a department marked critical, a position
    added, an objective saved. Called only *after* the caller's own
    transaction has committed, never before: enqueueing first and having
    the commit fail afterward would ask the worker to generate suggestions
    from data that was never actually saved.

    Args:
        organization_id: Organization to (re)generate suggestions for.
        ttl_seconds: How long a claim blocks a repeat trigger. Overridable
            only so tests don't have to wait out a real 60 seconds — every
            real caller uses the default.

    Returns:
        True if this call claimed the debounce key and enqueued a run.
        False if another call already claimed it within ``ttl_seconds`` —
        that recent trigger already covers this one.
    """
    debounce_key = f"ai_suggestions:debounce:{organization_id}"
    client = aioredis.from_url(settings.redis_url)
    try:
        acquired = await client.set(debounce_key, "1", nx=True, ex=ttl_seconds)
    finally:
        await client.aclose()

    if not acquired:
        logger.info("AI suggestion generation for org %s already queued; skipping", organization_id)
        return False

    celery.send_task(AI_GENERATE_SUGGESTIONS_TASK, args=[str(organization_id)])
    return True
