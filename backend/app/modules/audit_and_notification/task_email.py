"""The email that goes with a "a task landed on you" notification (08_DECISIONS.md 2026-11-14).

The notification inside the app is created by the Task module as before. For the two events that
need someone to act (a task is given to a person; a task has no owner yet) the Task module also calls
``email_people_about_task`` here, so the person hears about it even if they are not logged in.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.core.after_commit import run_after_commit
from app.core.celery_app import celery
from app.core.config import settings
from app.core.email import get_email_service
from app.modules.tenancy_identity.enums import AccountStatus
from app.modules.tenancy_identity.models import User

logger = logging.getLogger(__name__)


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def dispatch_task_email(self, email: str, title: str, body: str, task_link: str) -> None:
    """Send one task email, trying again a few times if delivery fails."""

    async def _send():
        await get_email_service().send_task_email(email, title, body, task_link)

    try:
        asyncio.run(_send())
        logger.info("Task email sent to %s", email)
    except Exception as exc:
        logger.error("Failed to send task email to %s: %s", email, exc)
        raise self.retry(exc=exc) from exc


def _queue_one(email: str, title: str, body: str, task_link: str):
    """Make the function that queues one email (a function per address, so each keeps its own values)."""

    def queue() -> None:
        dispatch_task_email.delay(email, title, body, task_link)

    return queue


async def email_people_about_task(db, user_ids: list[uuid.UUID], title: str, body: str, task_id: uuid.UUID) -> None:
    """Email each person about a task, once the request that caused it has been saved.

    Only people with a verified account get one (an account that was never verified cannot sign in
    to the link anyway). Addresses are looked up now; the sending is queued after the commit, so an
    email is never sent for work that was rolled back.
    """
    if not user_ids:
        return
    result = await db.execute(
        select(User.email).where(User.id.in_(user_ids), User.account_status == AccountStatus.VERIFIED.value)
    )
    task_link = f"{settings.app_url}/tasks/{task_id}"
    for address in result.scalars().all():
        run_after_commit(db, _queue_one(address, title, body, task_link))
