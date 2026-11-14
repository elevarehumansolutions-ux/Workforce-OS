"""Celery tasks that erase deleted companies for good, 30 days after they were deleted.

Built like ``scoring/tasks.py``:

- ``purge_scan`` is scheduled by Celery Beat once a day. It asks which deleted companies are old enough
  (the one cross-company read, through a narrow ``SECURITY DEFINER`` function) and queues one job each.
- ``purge_organization`` erases ONE company in its own transaction (``purge.py``). One company failing or
  retrying never holds up the others, and a repeat run is harmless: a company already gone is skipped.
"""

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.model_registry  # noqa: F401 - registers every model, as the app entrypoint does
from app.core.celery_app import celery
from app.core.config import settings

from .purge import PURGE_AFTER_DAYS, list_due_for_purge, purge_company

logger = logging.getLogger(__name__)

PURGE_SCAN_TASK = "app.modules.auth.purge_tasks.purge_scan"
PURGE_ORG_TASK = "app.modules.auth.purge_tasks.purge_organization"


async def _scan() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            organization_ids = await list_due_for_purge(db, PURGE_AFTER_DAYS)
        for organization_id in organization_ids:
            celery.send_task(PURGE_ORG_TASK, args=[str(organization_id)])
        return len(organization_ids)
    finally:
        await engine.dispose()


async def _purge(organization_id: uuid.UUID) -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            removed = await purge_company(db, organization_id, PURGE_AFTER_DAYS)
            return 0 if removed is None else sum(removed.values())
    finally:
        await engine.dispose()


@celery.task(bind=True, name=PURGE_SCAN_TASK, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def purge_scan(self) -> int:
    """Beat-scheduled, once a day: find and queue every deleted company that is due to be erased."""
    return asyncio.run(_scan())


@celery.task(bind=True, name=PURGE_ORG_TASK, autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def purge_organization(self, organization_id: str) -> int:
    """Erase one deleted company. Returns how many rows were removed (0 if it was skipped)."""
    return asyncio.run(_purge(uuid.UUID(organization_id)))
