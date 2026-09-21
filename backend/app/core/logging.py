"""Structured logging configuration built on structlog.

Wires structlog's processor pipeline into stdlib logging so both
structlog-native calls and third-party stdlib loggers (uvicorn, sqlalchemy)
render through the same formatter — colorized console output in
development, structured JSON elsewhere.
"""

import logging
import sys
from collections.abc import Sequence

import structlog
from structlog.types import Processor

from app.core.config import settings


def configure_logging(*, log_level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Colorized console output in development. Structured JSON everywhere
    else — Sentry and any log aggregator need actual fields to filter and
    search on, not a human-formatted string.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    json_logging = settings.environment != "development"

    # Each log event flows through these in order, like middleware
    shared_processors: Sequence[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        # Without this, a plain stdlib call like logger.info(msg, extra={...})
        # attaches those fields to the LogRecord, but nothing surfaces them
        # into the structured output — they'd be silently dropped.
        structlog.stdlib.ExtraAdder(),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Renders the final output format
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logging
        else structlog.dev.ConsoleRenderer(
            colors=True, exception_formatter=structlog.dev.plain_traceback
        )
    )

    # Configuring Structlog
    # We wrap shared_processors in ProcessorFormatter.wrap_for_formatter so they play nicely
    # with standard library logging, which expects handlers to receive BoundLogger instances.
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # This handles logs that come from third-party libraries
    # (e.g. uvicorn, sqlalchemy) that uses python's stdlib logging directly
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # Log output goes to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level)
    root_logger.addHandler(handler)

    # Global Context Binding
    structlog.contextvars.bind_contextvars(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
