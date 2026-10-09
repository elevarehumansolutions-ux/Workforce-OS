"""Celery tasks for the Task module: telling people when a task becomes overdue.

Built like ``attendance/tasks.py``. Two tasks:

- ``overdue_scan`` is scheduled by Celery Beat. It asks which organizations
  have an overdue task nobody has been told about (the one cross-tenant read,
  through a narrow ``SECURITY DEFINER`` function) and queues one job for each.
- ``announce_organization_overdue_tasks`` does the telling for ONE
  organization, under that organization's row-level security. One
  organization failing or retrying never holds up the others.

Each overdue task is announced once (``tasks.overdue_notified_at``), and again
only if its deadline later changes.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.model_registry  # noqa: F401 - registers every model, as the app entrypoint does
from app.core.celery_app import celery
from app.core.config import settings

from .repository import TaskRepository
from .service import TaskService

logger = logging.getLogger(__name__)

OVERDUE_SCAN_TASK = "app.modules.tasks.tasks.overdue_scan"
ANNOUNCE_ORG_TASK = "app.modules.tasks.tasks.announce_organization_overdue_tasks"


async def run_overdue_scan(db: AsyncSession) -> int:
    """Queue an announcement job for every organization with unannounced overdue tasks.

    Args:
        db: A session with no tenant context set (the lookup is cross-tenant).

    Returns:
        How many organizations were queued.
    """
    organization_ids = await TaskRepository(db).list_organizations_with_unannounced_overdue_tasks()
    for organization_id in organization_ids:
        celery.send_task(ANNOUNCE_ORG_TASK, args=[str(organization_id)])
    return len(organization_ids)


async def run_announce_for_organization(
    db: AsyncSession, organization_id: uuid.UUID, now: datetime | None = None
) -> int:
    """Announce one organization's overdue tasks, then commit once.

    A Celery task has no web request to set the tenant context, so this sets
    it first. After that, every query only sees this organization's rows.

    Args:
        db: A session to run in.
        organization_id: The organization to announce for.
        now: The current moment; tests pass a fixed one.

    Returns:
        How many tasks were announced.
    """
    if now is None:
        now = datetime.now(UTC)
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    announced = await TaskService(db).announce_overdue_tasks(organization_id, now)
    await db.commit()
    if announced:
        logger.info(
            "Overdue tasks announced",
            extra={"organization_id": str(organization_id), "announced_count": announced},
        )
    return announced


async def _scan() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_overdue_scan(db)
    finally:
        await engine.dispose()


async def _announce_organization(organization_id: uuid.UUID) -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_announce_for_organization(db, organization_id)
    finally:
        await engine.dispose()


@celery.task(
    bind=True,
    name=OVERDUE_SCAN_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def overdue_scan(self) -> int:
    """Beat-scheduled: find and queue every organization with unannounced overdue tasks."""
    return asyncio.run(_scan())


@celery.task(
    bind=True,
    name=ANNOUNCE_ORG_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def announce_organization_overdue_tasks(self, organization_id: str) -> int:
    """Announce one organization's overdue tasks; returns how many were announced.

    Safe to retry: the announcing and the marking happen in one transaction,
    so a failure announces nothing and marks nothing, and a rerun after a
    partial failure only picks up what is still unannounced.
    """
    return asyncio.run(_announce_organization(uuid.UUID(organization_id)))
