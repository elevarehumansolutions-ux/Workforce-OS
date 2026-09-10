"""FastAPI application entry point for the Elevare platform.

Configures middleware, exception handlers, and mounts all API routers.
The ``lifespan`` context manager handles startup (logging, DB ping) and
shutdown (engine disposal).
"""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
# import sentry_sdk
from fastapi import FastAPI
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# from slowapi import _rate_limit_exceeded_handler
# from slowapi.errors import RateLimitExceeded
# from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

# import app.core.model_registry  # noqa: F401
from app.core.config import settings
from app.core.database import engine

# Initialise Sentry before anything else
# if settings.sentry_dsn:
#     sentry_sdk.init(
#         dsn=settings.sentry_dsn,
#         environment=settings.environment,
#         release=settings.app_version,
#         traces_sample_rate=0.2,
#         profiles_sample_rate=0.1,
#     )
from app.core.exception_handler import (
    handle_generic_exception,
    handle_http_exception,
    handle_platform_exception,
    handle_pydantic_validation_error,
)
from app.core.exceptions import PlatformError
# from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events.

    Performs initialization (logging, connection pings) on startup and
    cleanup (session disposal) on shutdown.

    Args:
    ----
        app: The current FastAPI instance.

    Yields:
    ------
        None: Control to the application until shutdown.

    """
    configure_logging(log_level="DEBUG" if settings.debug else "INFO")

    # Startup
    logger.info(
        "Starting Elevare Workforce OS API",
        extra={"environment": settings.environment, "version": settings.app_version},
    )

    # Verify database connection — fail fast: an app that starts "successfully"
    # without a reachable database just defers the failure to the first
    # request, which is a more confusing place to discover it.
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception:
        logger.error("Database connection failed", exc_info=True)
        raise

    # Verify redis connection
    try:
        async with aioredis.from_url(settings.redis_url) as redis_client:
            await redis_client.ping()
            await redis_client.aclose()
            logger.info("Redis connection verified")
    except Exception:
        logger.error("Redis connection failed", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down %s", settings.app_name)
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# ---- Rate limiter state ----
# app.state.limiter = limiter

# ---- Global Middleware ----
# app.add_middleware(SlowAPIMiddleware)  # must be before other middleware
app.add_middleware(SecurityHeadersMiddleware, environment=settings.environment)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# ---- Exception Handlers ----

app.add_exception_handler(PlatformError, handle_platform_exception)
app.add_exception_handler(RequestValidationError, handle_pydantic_validation_error)
app.add_exception_handler(HTTPException, handle_http_exception)
app.add_exception_handler(Exception, handle_generic_exception)
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    tags=["system"],
)
async def health_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.error("Health check: database unreachable", exc_info=True)
        db_ok = False

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": "ok" if db_ok else "error",
            "database": "ok" if db_ok else "unreachable",
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )


# ---- Routers ----
