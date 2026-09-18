"""Generic, domain-agnostic security primitives.

Random token generation and one-way hashing — used by any module that needs
a single-use token pattern (email verification, password reset, teammate
invites). Lives in `core`, not `auth`, deliberately: it has nothing
auth-specific about it, and letting a non-auth module (e.g.
tenancy_identity) depend on `auth` just to hash a token would introduce a
cross-module dependency this codebase otherwise keeps strictly one-way
(auth depends on tenancy_identity, never the reverse).

Password hashing (bcrypt) stays in auth/security.py — that one genuinely is
an auth concern.
"""

import hashlib
import secrets


def generate_token() -> str:
    """Generate a secure random token.

    Returns:
        A URL-safe token string.
    """
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Return a SHA-256 hex digest of the raw token for safe DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()
