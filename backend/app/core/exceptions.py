"""Domain exceptions for the Elevare Workforce OS Platform.

All exceptions inherit from ``PlatformError``, which carries the HTTP status
code, machine-readable ``code``, and human-readable ``message`` needed by the
global exception handler to build a consistent ``ErrorResponse``.
"""


class PlatformError(Exception):
    """Base class for all application-level exceptions.

    Attributes
    ----------
        message: Human-readable description of the error.
        code: Upper-snake-case machine-readable identifier (e.g. ``NOT_FOUND``).
        status_code: HTTP status code to return to the client.
        details: Optional list of field-level error detail objects.

    """

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int,
        details: list | None = None
    ) -> None:
        """Set error attributes and pass the message to base Exception."""
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or None
        super().__init__(message)


# ---------------------------------------------------------------------------
# Authentication  (HTTP 401 / 403)
# ---------------------------------------------------------------------------


class InvalidCredentialsException(PlatformError):
    """Raised when email/password credentials do not match any account."""

    def __init__(
        self,
        message: str = "Invalid credentials",
        code: str = "INVALID_CREDENTIALS",
        status_code: int = 401,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class TokenExpiredException(PlatformError):
    """Raised when a JWT access or refresh token has passed its expiry time."""

    def __init__(
        self,
        message: str = "Token expired",
        code: str = "TOKEN_EXPIRED",
        status_code: int = 401,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class TokenInvalidException(PlatformError):
    """Raised when a JWT is malformed, has a bad signature, or wrong type."""

    def __init__(
        self,
        message: str = "Token is invalid",
        code: str = "TOKEN_INVALID",
        status_code: int = 401,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class RevokedTokenException(PlatformError):
    """Raised when a refresh token has already been revoked (used or logged out)."""

    def __init__(
        self,
        message: str = "Token revoked",
        code: str = "TOKEN_REVOKED",
        status_code: int = 401,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class RefreshTokenMissing(PlatformError):
    """Raised when a refresh token is expected but not present in the request."""

    def __init__(
        self,
        message: str = "Refresh token is missing",
        code: str = "REFRESH_TOKEN_MISSING",
        status_code: int = 401,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class AlreadyExistsException(PlatformError):
    """Raised when attempting to create a resource that already exists."""

    def __init__(
        self,
        message: str = "Resource already exists",
        code: str = "ALREADY_EXISTS",
        status_code: int = 409,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)



class TokenAlreadyUsedException(PlatformError):
    """Raised when a verification or invite token has already been consumed."""

    def __init__(
        self,
        message: str = "Token has already been used",
        code: str = "TOKEN_ALREADY_USED",
        status_code: int = 400,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


# ---------------------------------------------------------------------------
# Authorization  (HTTP 403)
# ---------------------------------------------------------------------------

class PermissionDeniedException(PlatformError):
    """Raised when an authenticated user lacks the required role or ownership."""

    def __init__(
        self,
        message: str = "Permission denied",
        code: str = "PERMISSION_DENIED",
        status_code: int = 403,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


# ---------------------------------------------------------------------------
# Validation  (HTTP 422)
# ---------------------------------------------------------------------------

class ValidationException(PlatformError):
    """Raised for business-rule validation failures (e.g. invalid state transitions)."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "VALIDATION_FAILED",
        status_code: int = 422,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)

