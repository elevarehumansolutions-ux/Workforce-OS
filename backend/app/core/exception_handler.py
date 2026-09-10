"""Global exception handlers for the Elevare platform.

Registered in ``main.py``, these handlers intercept specific exception
types raised anywhere in the application and return consistently
formatted ``ErrorResponse`` JSON bodies.

Each handler follows the same contract:
- Accept a ``Request`` and the raised exception.
- Build an ``ErrorResponse`` payload.
- Return a ``JSONResponse`` with the appropriate HTTP status code.
"""

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import PlatformError
from app.core.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


async def handle_platform_exception(
    request: Request,
    exc: PlatformError,
) -> JSONResponse:
    """Handle any ``Platform Errors`` subclass.

    Serialises the exception's structured metadata directly into the
    ``ErrorResponse`` envelope and returns it with the exception's own
    HTTP status code.

    Args:
        request: The incoming FastAPI request (unused but required by
            the handler signature).
        exc: The caught ``PlatformError`` instance.

    Returns:
        A ``JSONResponse`` containing the serialised ``ErrorResponse``.
    """
    content = ErrorResponse(
        code=exc.code,
        status="error",
        message=exc.message,
        details=exc.details,
    )

    return JSONResponse(status_code=exc.status_code, content=content.model_dump())


async def handle_pydantic_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic ``RequestValidationError`` raised by FastAPI.

    Flattens the list of Pydantic validation errors into ``ErrorDetail``
    objects, joining nested location parts with `` -> `` for readability.

    Args:
        request: The incoming FastAPI request (unused but required by
            the handler signature).
        exc: The caught ``RequestValidationError`` instance.

    Returns:
        A ``JSONResponse`` with HTTP 422 and a list of field-level errors.

    """
    error_details = []

    for error in exc.errors():
        field = " -> ".join(str(item) for item in error["loc"][1:]) or "body"
        error_details.append(ErrorDetail(field=field, message=error["msg"]))

    content = ErrorResponse(
        code="VALIDATION_ERROR",
        status="error",
        message="Validation failed",
        details=error_details,
    )

    return JSONResponse(
        status_code=422,
        content=content.model_dump(),
    )


async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Handle FastAPI ``HTTPException`` raised with any status.

    Respects the status code set in the exception (e.g. 401, 403, 404)
    rather than hardcoding to 404.

    Args:
        request: The incoming FastAPI request (unused but required by
            the handler signature).
        exc: The caught ``HTTPException`` instance.

    Returns:
        A ``JSONResponse`` with the exception's status code and an
        appropriate error response body.

    """
    _code_map = {
        401: "AUTHENTICATION_ERROR",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
    }
    code = _code_map.get(exc.status_code, "HTTP_ERROR")

    content = ErrorResponse(
        code=code,
        status="error",
        message=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=content.model_dump(),
    )


async def handle_generic_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle any unhandled exception as an internal server error.

    Logs the full traceback at ERROR level so it is captured by the
    application's logging pipeline, then returns a generic 500 response
    without leaking internal details to the client.

    Args:
        request: The incoming FastAPI request (unused but required by
            the handler signature).
        exc: The unhandled exception instance.

    Returns:
        A ``JSONResponse`` with HTTP 500 and an ``INTERNAL_SERVER_ERROR``
        error code.

    """
    logger.error("Unhandled exception", exc_info=True)
    content = ErrorResponse(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
    )
    return JSONResponse(
        status_code=500,
        content=content.model_dump(),
    )
