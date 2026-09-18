"""FastAPI dependency functions shared across all modules.

Provides:
- ``get_db``: yields an async database session per request.
- ``get_current_user``: extracts and validates the JWT, returns the authenticated User.
- ``require_role``: dependency factory that enforces role-based access control.
"""

from collections.abc import AsyncGenerator
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import (
    AccountBannedException,
    AccountDeactivatedException,
    AccountSuspendedException,
    EmailVerificationRequiredException,
    UserNotFoundException,
)
from app.modules.auth.jwt_handler import decode_access_token
from app.modules.tenancy_identity.enums import AccountStatus
from app.modules.tenancy_identity.models import User, Membership
from app.modules.tenancy_identity.service import MembershipService
from app.core.exceptions import InvalidCredentialsException, PermissionDeniedException


logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
# oauth2_scheme_optional = OAuth2PasswordBearer(
#     tokenUrl="/api/v1/auth/login", auto_error=False
# )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for the duration of a request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the bearer token and return the authenticated user.

    Enforces account status — raises for PENDING_VERIFICATION, SUSPENDED,
    BANNED, and DEACTIVATED. Use ``get_current_user_any_status`` on endpoints
    that must work regardless of status (e.g. GET /me, resend-verification).

    """
    payload = decode_access_token(token)

    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()

    if user is None:
        raise UserNotFoundException()

    # Enforce account status — every protected endpoint inherits this check
    status = user.account_status
    if status == AccountStatus.PENDING_VERIFICATION.value:
        raise EmailVerificationRequiredException()
    if status == AccountStatus.SUSPENDED.value:
        raise AccountSuspendedException()
    if status == AccountStatus.BANNED.value:
        raise AccountBannedException()
    if status == AccountStatus.DEACTIVATED.value:
        raise AccountDeactivatedException()

    return user

async def get_current_membership(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Membership:
    """Establish org context for this request and return the live membership
    the caller is acting under  re-checked against the DB, not just trusted
    from theh JWT's `role` claim

    """
    payload = decode_access_token(token)

    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(payload.org_id)}
    )
    
    membership = await MembershipService(db).get_membership(
        current_user.id,
        uuid.UUID(payload.org_id)
    )

    # Same error either way — a deactivated membership shouldn't be
    # distinguishable from a nonexistent one to the caller (08_DECISIONS.md
    # 2026-09-18: deactivation is scoped to this one membership, not the
    # user globally, so a token for a different, still-active org is
    # unaffected).
    if membership is None or membership.deactivated_at is not None:
        raise InvalidCredentialsException("Membership no longer exists")

    return membership

def require_org_role(*roles: str):
    """Dependency factory - restricts an endpoint to specific membership roles."""

    async def _check(membership: Membership = Depends(get_current_membership)) -> Membership:
        if membership.role not in roles:
            raise PermissionDeniedException("Insufficient permissions")
        
        return membership
    
    return _check

async def require_owner(
    membership: Membership = Depends(get_current_membership),
) -> Membership:
    """Restricts an endpoint to the organization's Owner."""
    if not membership.is_owner:
        raise PermissionDeniedException()
    return membership
