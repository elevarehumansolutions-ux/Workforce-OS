"""Domain exceptions for the Elevare Workforce OS Platform.

All exceptions inherit from ``PlatformError``, which carries the HTTP status
code, machine-readable ``code``, and human-readable ``message`` needed by the
global exception handler to build a consistent ``ErrorResponse``.
"""


class PlatformError(Exception):
    """Base class for all application-level exceptions.

    Attributes:
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
        # Always a list, never None — ErrorResponse.details is typed
        # list[ErrorDetail] = [], and every PlatformError subclass in this
        # codebase is raised without an explicit `details=`, so `details or
        # None` was crashing the global handler (handle_platform_exception)
        # into a 500 on every single error response it tried to serialise.
        self.details = details or []
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


class ResourceInUseException(PlatformError):
    """Raised when deletion is blocked because the resource is still in use.

    Still actively referenced elsewhere (01_REQUIREMENTS.md §2,
    08_DECISIONS.md 2026-09-07: block, don't cascade — the message carries
    the specific, named reason, not a generic 'cannot delete').
    """

    def __init__(
        self,
        message: str = "Resource is still in use",
        code: str = "RESOURCE_IN_USE",
        status_code: int = 409,
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


class VerificationTokenExpiredException(PlatformError):
    """Raised when a verification or invite token has passed its expiry time."""

    def __init__(
        self,
        message: str = "Verification token has expired",
        code: str = "VERIFICATION_TOKEN_EXPIRED",
        status_code: int = 400,
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


class EmailVerificationRequiredException(PlatformError):
    """Raised when an account with PENDING_VERIFICATION status tries to use a protected endpoint."""

    def __init__(
        self,
        message: str = "Email verification required",
        code: str = "EMAIL_VERIFICATION_REQUIRED",
        status_code: int = 403,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class AccountSuspendedException(PlatformError):
    """Raised when a SUSPENDED account tries to use a protected endpoint."""

    def __init__(
        self,
        message: str = "Account suspended",
        code: str = "ACCOUNT_SUSPENDED",
        status_code: int = 403,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class AccountBannedException(PlatformError):
    """Raised when a BANNED account tries to use a protected endpoint."""

    def __init__(
        self,
        message: str = "Account banned",
        code: str = "ACCOUNT_BANNED",
        status_code: int = 403,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class AccountDeactivatedException(PlatformError):
    """Raised when a DEACTIVATED account tries to use a protected endpoint."""

    def __init__(
        self,
        message: str = "Account deactivated",
        code: str = "ACCOUNT_DEACTIVATED",
        status_code: int = 403,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class NoActiveMembershipException(PlatformError):
    """Raised at login when every membership the user has is deactivated.

    The user's account itself is fine, but every organization they belong
    to has deactivated their specific membership (08_DECISIONS.md
    2026-09-18: deactivation is per-membership, not a global account lock —
    this is the legitimate, expected outcome of that, not a server error).
    """

    def __init__(
        self,
        message: str = "You have no active organization memberships",
        code: str = "NO_ACTIVE_MEMBERSHIP",
        status_code: int = 403,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


# ---------------------------------------------------------------------------
# Authorization  (HTTP 403 / 404)
# ---------------------------------------------------------------------------

class UserNotFoundException(PlatformError):
    """Raised when a lookup by user id/email finds no matching row."""

    def __init__(
        self,
        message: str = "User not found",
        code: str = "USER_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class NotificationNotFoundException(PlatformError):
    """Raised when a lookup by notification id finds no matching row.

    This also covers "exists, but belongs to a different user" — same
    reasoning as MembershipNotFoundException: a caller shouldn't be able to
    tell "not yours" apart from "doesn't exist".
    """

    def __init__(
        self,
        message: str = "Notification not found",
        code: str = "NOTIFICATION_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class LocationNotFoundException(PlatformError):
    """Raised when a lookup by location id finds no matching row.

    Also covers "exists, but belongs to a different org" — RLS makes that
    indistinguishable from not existing, same reasoning as
    MembershipNotFoundException.
    """

    def __init__(
        self,
        message: str = "Location not found",
        code: str = "LOCATION_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class DepartmentNotFoundException(PlatformError):
    """Raised when a lookup by department id finds no matching row."""

    def __init__(
        self,
        message: str = "Department not found",
        code: str = "DEPARTMENT_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class PositionNotFoundException(PlatformError):
    """Raised when a lookup by position id finds no matching row."""

    def __init__(
        self,
        message: str = "Position not found",
        code: str = "POSITION_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class EmployeeNotFoundException(PlatformError):
    """Raised when a lookup by employee id finds no matching row."""

    def __init__(
        self,
        message: str = "Employee not found",
        code: str = "EMPLOYEE_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class MembershipNotFoundException(PlatformError):
    """Raised when a lookup by membership id finds no matching row.

    This also covers "exists, but belongs to a different org" — RLS makes
    that case indistinguishable from not existing at all, which is correct:
    a caller shouldn't be able to tell the two apart.
    """

    def __init__(
        self,
        message: str = "Membership not found",
        code: str = "MEMBERSHIP_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class BusinessDNANotFoundException(PlatformError):
    """Raised when the org hasn't created a Business DNA profile yet.

    Also covers "exists, but belongs to a different org" — RLS makes that
    indistinguishable from not existing, same reasoning as
    LocationNotFoundException.
    """

    def __init__(
        self,
        message: str = "Business DNA not found",
        code: str = "BUSINESS_DNA_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class BusinessDNACoreValueNotFoundException(PlatformError):
    """Raised when a lookup by core value id finds no matching row."""

    def __init__(
        self,
        message: str = "Business DNA core value not found",
        code: str = "BUSINESS_DNA_CORE_VALUE_NOT_FOUND",
        status_code: int = 404,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


class InternalServerErrorException(PlatformError):
    """Raised when an unexpected error occurs that isn't a known domain failure."""

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        details: list | None = None,
    ) -> None:
        """Initialise with platform error defaults."""
        super().__init__(message, code, status_code, details)


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

