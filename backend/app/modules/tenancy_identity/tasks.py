"""Asynchronous Celery tasks for the tenancy_identity module.

Lives here rather than in auth/tasks.py so this module never imports from
auth — the dependency direction stays one-way (auth depends on
tenancy_identity, never the reverse). See auth/tasks.py for the equivalent
verification/password-reset email tasks.
"""

import logging

from app.core.celery_app import celery
from app.core.email import get_email_service

logger = logging.getLogger(__name__)


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def dispatch_invite_email(
    self, email: str, invite_link: str, company_name: str | None = None
) -> None:
    """Send a teammate-invite email with retry logic."""
    import asyncio

    async def _send():
        service = get_email_service()
        await service.send_invite_email(email, invite_link, company_name=company_name)

    try:
        asyncio.run(_send())
        logger.info(f"Invite email sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send invite email to {email}: {exc}")
        raise self.retry(exc=exc) from exc
