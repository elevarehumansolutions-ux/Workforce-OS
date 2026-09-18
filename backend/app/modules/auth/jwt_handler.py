"""JWT creation and decoding utilities for the Elevare auth system.

Public interface:
- ``create_token_pair`` - generates both access and refresh tokens for a user.
- ``decode_access_token`` - Validates an access token and returns a typed payload

Internal helpers (``_create_acccess_token`` and ``_create_refresh_token``) are prefixed with ``_`` and should not be called directly outside this module.
"""

import uuid
from datetime import UTC, timedelta, datetime

from jose import jwt, ExpiredSignatureError, JWTError

from app.core.config import settings
from app.core.exceptions import TokenExpiredException, TokenInvalidException
from app.core.schemas import TokenPayload


def _create_access_token(data: dict) -> str:
    payload = data.copy()
    payload.update({
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "type": "access",
    })
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.algorithm,
    )


def _create_refresh_token(data: dict) -> str:
    """Create a refresh token."""
    payload = data.copy()
    payload.update({
        "exp": datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.algorithm,
    )


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token.

    Args:
        token: The encoded JWT string from the Authorization header.

    Returns:
        A ``TokenPayload`` with ``sub``, ``role``, and ``type``.

    Raises:
        TokenExpiredException: If the token's ``exp`` claim is in the past.
        TokenInvalidException: If the token is malformed, has a bad signature,
            or is not an access token.

    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.algorithm],
        )
    except ExpiredSignatureError:
        raise TokenExpiredException()  # type: ignore
    except JWTError as e:
        raise TokenInvalidException(str(e))  # type: ignore

    # Type-check payload into TokenPayload before returning
    try:
        # `sub` must be a string (UUID) and `type` must be "access"
        decoded_payload = TokenPayload(
            sub=str(payload["sub"]),
            org_id=payload.get("org_id", ""),
            role=payload.get("role", ""),
            type=payload.get("type", ""),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise TokenInvalidException(f"Invalid token payload: {e}")  # type: ignore

    if decoded_payload.type != "access":
        raise TokenInvalidException("Token is not an access token")  # type: ignore

    return decoded_payload

def decode_refresh_token(token: str) -> TokenPayload:
    """Decode a refresh token without checking expiry (expiry checked via DB record).

    Args:
        token: The encoded JWT refresh token string.

    Returns:
        A ``TokenPayload`` with ``sub``, ``role``, and ``type``.

    Raises:
        TokenInvalidException: If the token is malformed or has a bad signature.

    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.algorithm],
            # the token's expiration is being managed and enforced through a
            # database record instead of the token payload itself.
            options={"verify_exp": False},  # expiry is enforced via DB record
        )
    except JWTError:
        raise TokenInvalidException() from None

    if payload.get("type") != "refresh":
        raise TokenInvalidException()

    try:
        return TokenPayload(
            sub=payload["sub"],
            role=payload["role"],
            org_id=payload.get("org_id", ""),
            type=payload["type"],
        )
    except (KeyError, ValueError, TypeError) as e:
        raise TokenInvalidException(f"Invalid token payload: {e}")  # type: ignore


def create_token_pair(user_id: str, org_id: str, role: str) -> dict:
    """Generate an access/refresh token pair for a user.

    Args:
        user_id: The user's UUID as a string — becomes the ``sub`` claim.
        role: The user's role string — embedded in both tokens.

    Returns:
        A dict with ``access_token``, ``refresh_token``, and ``token_type``.

    """
    data = {"sub": str(user_id), "org_id": str(org_id), "role": role}

    return {
        "access_token": _create_access_token(data),
        "refresh_token": _create_refresh_token(data),
        "token_type": "bearer",
    }

