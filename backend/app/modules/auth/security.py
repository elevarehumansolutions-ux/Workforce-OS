"""Password hashing utilities for authentication.

Wraps ``bcrypt`` for password operations. Generic token generation/hashing
(used for email verification, password reset, and invite tokens) lives in
``app.core.security`` instead — see that module's docstring for why.
"""

import bcrypt

_ROUNDS = 12


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plain-text password.

    Args:
        password: The raw password string supplied by the user.

    Returns:
        A bcrypt-hashed string safe to store in the database.

    """
    return bcrypt.hashpw(
        password.encode(),
        bcrypt.gensalt(rounds=_ROUNDS)
    ).decode()

def verify_password(plain: str, hashed: str) -> bool:
    """Verify that the plain-text password matches the hash.

    Args:
        plain: The raw password.
        hashed: The hashed password.
    
    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain.encode(), hashed.encode())

