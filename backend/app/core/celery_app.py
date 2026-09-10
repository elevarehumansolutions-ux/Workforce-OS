"""Celery application configuration for the Workforce OS.

This module initializes the Celery app instance and configures it with
Redis as both the message broker and result backend. It also sets
default task execution policies (timeouts, serialization, etc.).
"""

import logging

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)


def _redis_url_with_ssl(url: str) -> str:
    """Append ssl_cert_reqs=CERT_NONE for rediss:// URLs (required by Celery)."""
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}ssl_cert_reqs=CERT_NONE"
    return url


_broker_url = _redis_url_with_ssl(settings.redis_url)
_backend_url = _redis_url_with_ssl(settings.redis_url)

celery = Celery(
    "Elevare Workforce",
    broker=_broker_url,
    backend=_backend_url,
    include=[],
)

# Celery configuration
celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result backend
    result_expires=3600,
    # Task execution
    task_always_eager=False,  # Always run tasks in the worker, never inline
    task_track_started=True,
    task_time_limit=300,  # Hard kill after 5 minutes
    task_soft_time_limit=240,  # Warn after 4 minutes
    # Worker
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    beat_schedule={},
)
