"""Shared Pydantic schema models used across the application.

Provides reusable response and error structures that are referenced by
multiple apps rather than belonging to any single domain module.
"""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """A single field-level error detail returned in validation responses.

    Attributes:
        field: The name of the input field that failed validation.
        message: Human-readable explanation of why the field is invalid.

    """

    field: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error envelope returned by all API error handlers.

    Attributes:
        code: Machine-readable upper-snake-case error identifier.
        message: Human-readable summary of the error.
        details: Optional list of field-level ``ErrorDetail`` objects,
            populated for validation errors.

    """

    code: str
    status: Literal["error"] = "error"
    message: str
    details: list[ErrorDetail] = []


class TokenPayload(BaseModel):
    """Decoded JWT access token payload.

    Attributes:
        sub: Subject — the user's UUID as a string.
        role: The user's role embedded at token creation time.
        type: Token type; must be ``"access"`` for access tokens.

    """

    sub: str
    role: str
    type: str


class SuccessResponse(BaseModel):
    """Standard success envelope returned by all API success handlers.

    Attributes:
        code: Machine-readable upper-snake-case success identifier.
        message: Human-readable summary of the error.
        data: Optional field for returning arbitrary response data.

    """

    status: Literal["success"] = "success"
    message: str
    data: Any | None = None


class PaginationMeta(BaseModel):
    """Metadata for a paginated response page."""

    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginationResponse(BaseModel):
    """Standard paginated list response envelope."""

    status: Literal["success"] = "success"
    message: str
    data: list[Any]
    pagination: PaginationMeta
