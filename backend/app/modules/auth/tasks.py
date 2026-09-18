"""Asynchronous Celery tasks for sending email notifications.

Uses centralized email utilities to send formatted emails for
verification, password resets, and other system alerts.
Also creates in-app Notification records for user-facing events.
"""

import logging

from app.core.celery_app import celery
from app.core.email import get_email_service

logger = logging.getLogger(__name__)


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def dispatch_verification_email(
    self, token: str, email: str, next_url: str | None = None
) -> None:
    """Send account verification email with retry logic."""
    import asyncio

    async def _send():
        service = get_email_service()
        await service.send_verification_email(email, token, next_url=next_url)

    try:
        asyncio.run(_send())
        logger.info(f"Verification email sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send verification email to {email}: {exc}")
        raise self.retry(exc=exc) from exc


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def dispatch_password_reset_email(self, token: str, email: str) -> None:
    """Send password reset email with retry logic."""
    import asyncio

    async def _send():
        service = get_email_service()
        await service.send_password_reset_email(email, token)

    try:
        asyncio.run(_send())
        logger.info(f"Password reset email sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send password reset email to {email}: {exc}")
        raise self.retry(exc=exc) from exc

