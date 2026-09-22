"""Custom Starlette middleware for the Elevare Workforce OS.

Currently provides:
- ``RequestLoggingMiddleware``: logs every inbound request and its
  completed response, tagged with a request ID.
"""

import logging
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)



class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add HTTP security headers to every response.

    Headers applied:
    - X-Content-Type-Options: prevents MIME-type sniffing
    - X-Frame-Options: prevents clickjacking via iframes
    - X-XSS-Protection: legacy XSS filter for older browsers
    - Referrer-Policy: limits referrer info sent to third parties
    - Permissions-Policy: disables browser features not needed by this API
    - Strict-Transport-Security: enforces HTTPS (only set when not in debug mode)
    - Content-Security-Policy: restricts resource loading for API responses
    """

    def __init__(self, app, environment: str = "development") -> None:
        """Initialise the middleware and decide whether HSTS should be enforced.

        HSTS is set for every environment except development — same
        derivation as Settings.cookie_secure, so this can't drift out of
        sync with it the way an independent debug flag could (see
        03_ARCHITECTURE.md; DEBUG=true in production is already a case
        config.py's own validator treats as a real misconfiguration).
        """
        super().__init__(app)
        self._enforce_hsts = environment != "development"

    # FastAPI's own docs UI (only ever mounted when DEBUG=true — see
    # main.py's docs_url/redoc_url) is a real HTML+JS+CSS page, unlike
    # every other route here, which is pure JSON. The blanket
    # default-src 'none' CSP below is correct for the actual API (it has
    # no legitimate reason to load a script or stylesheet at all) but
    # silently breaks Swagger/ReDoc's own CDN-loaded JS — the page loads
    # (200 OK) but nothing in it ever renders. Exempted here rather than
    # weakened for every route, so the real API surface keeps the strict
    # policy unchanged.
    _CSP_EXEMPT_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Add security headers to every response."""
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        if request.url.path not in self._CSP_EXEMPT_PATHS:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        # HSTS — only over HTTPS, not in local dev
        if self._enforce_hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # NOTE: no "remove server banner" step here — Uvicorn sets the
        # Server header at the ASGI-server/transport layer, after this
        # app's Response object has already been built, so nothing here
        # can see or remove it. Suppressing it is a Uvicorn startup option
        # (`--no-server-header` / `server_header=False`), to be set where
        # the process actually starts (Dockerfile CMD / uvicorn.run), not here.

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every inbound request and its completed response with a request ID."""
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Log request start, call the next handler, then log completion or failure."""
        # Skip logging the CORS preflight requests
        if request.method == "OPTIONS":
            return await call_next(request)

        request_id = request.headers.get("X-REQUEST-ID") or str(uuid.uuid4())

        # Clear before bind: each request should start from an empty context,
        # never inherit contextvars left over from a previous one.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        logger.info(
            "Request started | request_id=%s method=%s path=%s client_ip=%s",
            request_id,
            request.method,
            request.url.path,
            request.client.host if request.client else "Unknown",
        )

        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                "Request failed | request_id=%s duration_ms=%.2f",
                request_id,
                process_time,
                exc_info=True,
            )

            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": [],
                },
                headers={"X-Request-ID": request_id},
            )
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Request-ID"] = request_id

        process_time = (time.time() - start_time) * 1000
        logger.info(
            "Request completed | request_id=%s status_code=%s duration_ms=%.2f",
            request_id,
            response.status_code,
            process_time,
        )

        return response

