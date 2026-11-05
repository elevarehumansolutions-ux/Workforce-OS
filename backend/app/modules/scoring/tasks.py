"""Celery tasks for the Scoring module: the nightly job that keeps scores up to date, and the weekly summary.

Built like ``tasks/tasks.py``. The nightly scoring has two tasks:

- ``scoring_nightly`` is scheduled by Celery Beat. It asks which organizations
  can have a score (the one cross-tenant read, through a narrow
  ``SECURITY DEFINER`` function) and queues one job for each.
- ``score_organization`` does the work for ONE organization, under that
  organization's row-level security: it closes the previous fiscal quarter if it
  is not closed yet, then refreshes the current one. One organization failing or
  retrying never holds up the others.

Safe to run late or twice: a closed quarter is judged at its own end and is
skipped once frozen (08_DECISIONS.md 2026-10-21, question 4).

The executive summary has two more: ``summary_weekly`` (Beat, Mondays) queues
``summarize_organization`` for each organization, which writes the final summary of a
quarter that just closed and this week's "so far" one (question 10).
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.model_registry  # noqa: F401 - registers every model, as the app entrypoint does
from app.core.celery_app import celery
from app.core.config import settings

from .repository import ScoringRepository
from .service import ScoringService
from .summary_service import ExecutiveSummaryService

logger = logging.getLogger(__name__)

SCORING_NIGHTLY_TASK = "app.modules.scoring.tasks.scoring_nightly"
SCORE_ORG_TASK = "app.modules.scoring.tasks.score_organization"
SUMMARY_WEEKLY_TASK = "app.modules.scoring.tasks.summary_weekly"
SUMMARY_ORG_TASK = "app.modules.scoring.tasks.summarize_organization"


async def run_scoring_scan(db: AsyncSession) -> int:
    """Queue a scoring job for every organization that can have a score.

    Args:
        db: A session with no tenant context set (the lookup is cross-tenant).

    Returns:
        How many organizations were queued.
    """
    organization_ids = await ScoringRepository(db).list_organizations_needing_scoring()
    for organization_id in organization_ids:
        celery.send_task(SCORE_ORG_TASK, args=[str(organization_id)])
    return len(organization_ids)


async def run_scoring_for_organization(
    db: AsyncSession, organization_id: uuid.UUID, now: datetime | None = None
) -> dict:
    """Run one organization's whole night, then commit once.

    A Celery task has no web request to set the tenant context, so this sets
    it first. After that, every query only sees this organization's rows. The
    closing and the refreshing happen in one transaction: a failure saves
    nothing, and the retry starts clean.

    Args:
        db: A session to run in.
        organization_id: The organization to score.
        now: The current moment; tests pass a fixed one.

    Returns:
        ``{"closed_previous_period": bool}``.
    """
    if now is None:
        now = datetime.now(UTC)
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    result = await ScoringService(db).run_nightly(organization_id, now)
    await db.commit()
    logger.info(
        "Scoring finished",
        extra={"organization_id": str(organization_id), "closed_previous_period": result["closed_previous_period"]},
    )
    return result


async def _scan() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_scoring_scan(db)
    finally:
        await engine.dispose()


async def _score_organization(organization_id: uuid.UUID) -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_scoring_for_organization(db, organization_id)
    finally:
        await engine.dispose()


async def run_summary_scan(db: AsyncSession) -> int:
    """Queue a summary job for every organization that can have a score (same cross-tenant lookup)."""
    organization_ids = await ScoringRepository(db).list_organizations_needing_scoring()
    for organization_id in organization_ids:
        celery.send_task(SUMMARY_ORG_TASK, args=[str(organization_id)])
    return len(organization_ids)


async def run_summary_for_organization(
    db: AsyncSession, organization_id: uuid.UUID, now: datetime | None = None
) -> dict:
    """One organization's weekly summary work: the final one for a quarter that just closed, then this week's.

    Committed in two steps on purpose: a final summary is written once, so it is
    saved before the "so far" one starts. If the second step fails and retries,
    the first is not paid for again.

    Returns:
        ``{"final": ..., "current": ...}`` with what happened in each step.
    """
    if now is None:
        now = datetime.now(UTC)
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    service = ExecutiveSummaryService(db)

    final = await service.finalize_previous(organization_id, now)
    await db.commit()

    # Committing ends the transaction, which clears the tenant setting, so set it again.
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    current = await service.refresh_current(organization_id, now)
    await db.commit()

    logger.info(
        "Executive summary job finished",
        extra={"organization_id": str(organization_id), "final": final, "current": current},
    )
    return {"final": final, "current": current}


async def _summary_scan() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_summary_scan(db)
    finally:
        await engine.dispose()


async def _summarize_organization(organization_id: uuid.UUID) -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_summary_for_organization(db, organization_id)
    finally:
        await engine.dispose()


# Retry only when the call never reached a real answer (same rule as AI suggestions and the blueprint).
# An unusable answer (LLMOutputError) fails the run instead of being retried.
_RETRYABLE_ANTHROPIC_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


@celery.task(bind=True, name=SUMMARY_WEEKLY_TASK, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def summary_weekly(self) -> int:
    """Beat-scheduled, once a week: find and queue every organization that can have a summary."""
    return asyncio.run(_summary_scan())


@celery.task(
    bind=True,
    name=SUMMARY_ORG_TASK,
    autoretry_for=_RETRYABLE_ANTHROPIC_ERRORS,
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=240,
)
def summarize_organization(self, organization_id: str) -> dict:
    """Write the final summary of a just-closed quarter and this week's "so far" one, for one organization."""
    return asyncio.run(_summarize_organization(uuid.UUID(organization_id)))


@celery.task(
    bind=True,
    name=SCORING_NIGHTLY_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def scoring_nightly(self) -> int:
    """Beat-scheduled: find and queue every organization that can have a score."""
    return asyncio.run(_scan())


@celery.task(
    bind=True,
    name=SCORE_ORG_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def score_organization(self, organization_id: str) -> dict:
    """Close the previous quarter if needed and refresh the current one, for one organization.

    Safe to retry: the whole night is one transaction, so a failure saves
    nothing, and a rerun finds a closed quarter already frozen.
    """
    return asyncio.run(_score_organization(uuid.UUID(organization_id)))
