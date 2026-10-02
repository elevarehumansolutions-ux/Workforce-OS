"""Celery tasks for attendance: the nightly auto-close of forgotten clock-outs.

Two tasks, mirroring the Quarterly Objective Review's shape (ai/tasks.py):

- ``auto_close_attendance`` is Beat-scheduled. It asks which organizations
  have anyone still clocked in (the one cross-tenant read, through a narrow
  ``SECURITY DEFINER`` function) and enqueues one task per organization.
- ``auto_close_organization_attendance`` does the closing for one
  organization, under that organization's RLS context. One organization
  failing or retrying never holds up the others.
"""

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.model_registry  # noqa: F401 - registers every model, as the app entrypoint does
from app.core.celery_app import celery
from app.core.config import settings

from .repository import AttendanceRepository
from .service import AttendanceService

logger = logging.getLogger(__name__)

AUTO_CLOSE_TASK = "app.modules.attendance.tasks.auto_close_attendance"
AUTO_CLOSE_ORG_TASK = "app.modules.attendance.tasks.auto_close_organization_attendance"


async def run_auto_close_scan(db: AsyncSession) -> int:
    """Enqueue an auto-close task for every organization that has anyone clocked in.

    Runs hourly (see the Beat schedule in ``core/celery_app.py``) because
    organizations sit in different timezones, so their midnights fall at
    different hours. Each per-organization task works out that organization's
    own most recent midnight and closes whatever clocked in before it, so a
    run that finds nothing past midnight yet simply closes nothing, and
    organizations with nobody clocked in are never enqueued at all.

    Args:
        db: A session with no tenant context set (the lookup is cross-tenant).

    Returns:
        How many organizations were enqueued.
    """
    organizations = await AttendanceRepository(db).list_organizations_with_open_records()
    for organization_id, _timezone in organizations:
        celery.send_task(AUTO_CLOSE_ORG_TASK, args=[str(organization_id)])
    return len(organizations)


async def run_auto_close_for_organization(
    db: AsyncSession, organization_id: uuid.UUID, now: datetime | None = None
) -> int:
    """Close one organization's stale open records, then commit once.

    Sets the organization's RLS context itself (a Celery task has no
    request to do it), so every query below sees only this organization.

    Args:
        db: A session to run in.
        organization_id: Organization to close records for.
        now: The current moment; injectable so tests can fix the clock.

    Returns:
        How many records were closed.
    """
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    closed = await AttendanceService(db).auto_close_stale_records(organization_id, now)
    await db.commit()
    if closed:
        logger.info(
            "Attendance auto-closed",
            extra={"organization_id": str(organization_id), "closed_count": closed},
        )
    return closed


async def _scan() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_auto_close_scan(db)
    finally:
        await engine.dispose()


async def _close_organization(organization_id: uuid.UUID) -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_auto_close_for_organization(db, organization_id)
    finally:
        await engine.dispose()


@celery.task(
    bind=True,
    name=AUTO_CLOSE_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def auto_close_attendance(self) -> int:
    """Beat-scheduled: find and enqueue every organization with anyone still clocked in.

    Retries broadly: this only does infrastructure work (one DB read, some
    Redis publishes), so every failure is plausibly transient, matching this
    codebase's convention for infra-only tasks.
    """
    return asyncio.run(_scan())


@celery.task(
    bind=True,
    name=AUTO_CLOSE_ORG_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def auto_close_organization_attendance(self, organization_id: str) -> int:
    """Close one organization's forgotten clock-outs; returns how many were closed.

    Safe to retry: the close is a conditional UPDATE, so a rerun after a
    partial failure closes only what is still open.
    """
    return asyncio.run(_close_organization(uuid.UUID(organization_id)))
