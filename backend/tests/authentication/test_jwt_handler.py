"""Unit tests for JWT creation/decoding. No DB needed — pure token logic."""

import time
import uuid

import pytest
from jose import jwt

from app.core.config import settings
from app.core.exceptions import TokenExpiredException, TokenInvalidException
from app.modules.auth.jwt_handler import (
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
)


def test_create_token_pair_round_trips_through_decode():
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    pair = create_token_pair(user_id=user_id, org_id=org_id, role="hr_administrator")

    payload = decode_access_token(pair["access_token"])

    assert payload.sub == user_id
    assert payload.org_id == org_id
    assert payload.role == "hr_administrator"
    assert payload.type == "access"


def test_decode_access_token_rejects_expired_token():
    expired = jwt.encode(
        {
            "sub": "x", "org_id": "y", "role": "employee", "type": "access",
            "exp": time.time() - 10,
        },
        settings.jwt_secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(TokenExpiredException):
        decode_access_token(expired)


def test_decode_access_token_rejects_bad_signature():
    token = jwt.encode(
        {
            "sub": "x", "org_id": "y", "role": "employee", "type": "access",
            "exp": time.time() + 60,
        },
        "a-completely-different-secret-key",
        algorithm=settings.algorithm,
    )
    with pytest.raises(TokenInvalidException):
        decode_access_token(token)


def test_decode_access_token_rejects_a_refresh_token():
    """A refresh token must not work as an access token, even though both
    are signed with the same secret — the `type` claim is what separates them."""
    pair = create_token_pair(user_id=str(uuid.uuid4()), org_id=str(uuid.uuid4()), role="employee")
    with pytest.raises(TokenInvalidException):
        decode_access_token(pair["refresh_token"])


def test_decode_refresh_token_rejects_an_access_token():
    pair = create_token_pair(user_id=str(uuid.uuid4()), org_id=str(uuid.uuid4()), role="employee")
    with pytest.raises(TokenInvalidException):
        decode_refresh_token(pair["access_token"])


def test_decode_refresh_token_ignores_jwt_expiry_claim():
    """Refresh token expiry is enforced via its DB record (RefreshToken.expires_at),
    not the JWT's own `exp` claim — decode_refresh_token must not reject a
    JWT-expired-but-DB-valid token on that basis alone."""
    expired_refresh = jwt.encode(
        {
            "sub": "x", "org_id": "y", "role": "employee", "type": "refresh",
            "jti": str(uuid.uuid4()), "exp": time.time() - 10,
        },
        settings.jwt_secret_key,
        algorithm=settings.algorithm,
    )
    payload = decode_refresh_token(expired_refresh)
    assert payload.type == "refresh"


def test_decode_refresh_token_rejects_bad_signature():
    token = jwt.encode(
        {
            "sub": "x", "org_id": "y", "role": "employee", "type": "refresh",
            "jti": str(uuid.uuid4()), "exp": time.time() + 60,
        },
        "a-completely-different-secret-key",
        algorithm=settings.algorithm,
    )
    with pytest.raises(TokenInvalidException):
        decode_refresh_token(token)


def test_decode_access_token_rejects_garbage_string():
    with pytest.raises(TokenInvalidException):
        decode_access_token("this-is-not-a-jwt-at-all")
