"""FastAPI dependency functions shared across all modules.

Provides:
- ``get_db``: yields an async database session per request.
- ``get_current_user``: extracts and validates the JWT, returns the authenticated User.
- ``require_role``: dependency factory that enforces role-based access control.
"""

import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
# from app.core.exceptions import (
#     AccountBannedException,
#     AccountDeactivatedException,
#     AccountSuspendedException,
#     EmailVerificationRequiredException,
#     PermissionDeniedException,
#     UserNotFoundException,
# )
# from app.modules.auth.jwt_handler import decode_access_token
# from app.modules.users.models import User

logger = logging.getLogger(__name__)

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
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


# async def get_current_user(
#     token: str = Depends(oauth2_scheme),
#     db: AsyncSession = Depends(get_db),
# ) -> User:
#     """Decode the bearer token and return the authenticated user.

#     Enforces account status — raises for PENDING_VERIFICATION, SUSPENDED,
#     BANNED, and DEACTIVATED. Use ``get_current_user_any_status`` on endpoints
#     that must work regardless of status (e.g. GET /me, resend-verification).

#     """
#     payload = decode_access_token(token)

#     result = await db.execute(
#         select(User)
#         .options(selectinload(User.organization))
#         .where(User.id == payload.sub)
#     )
#     user = result.scalar_one_or_none()

#     if user is None:
#         raise UserNotFoundException()

#     # Enforce account status — every protected endpoint inherits this check
#     status = user.account_status
#     if status == AccountStatus.PENDING_VERIFICATION.value:
#         raise EmailVerificationRequiredException()
#     if status == AccountStatus.SUSPENDED.value:
#         raise AccountSuspendedException()
#     if status == AccountStatus.BANNED.value:
#         raise AccountBannedException()
#     if status == AccountStatus.DEACTIVATED.value:
#         raise AccountDeactivatedException()

#     return user


# async def get_current_user_any_status(
#     token: str = Depends(oauth2_scheme),
#     db: AsyncSession = Depends(get_db),
# ) -> User:
#     """Like get_current_user but skips account status enforcement.

#     Use only on endpoints that must be reachable regardless of account status,
#     such as GET /me (needed by the frontend to render restricted-account UI)
#     and POST /resend-verification-email.

#     """
#     payload = decode_access_token(token)

#     result = await db.execute(
#         select(User)
#         .options(selectinload(User.organization))
#         .where(User.id == payload.sub)
#     )
#     user = result.scalar_one_or_none()

#     if user is None:
#         raise UserNotFoundException()

#     return user


# async def get_optional_user(
#     token: str | None = Depends(oauth2_scheme_optional),
#     db: AsyncSession = Depends(get_db),
# ) -> User | None:
#     """Return the authenticated user if a valid bearer token is present, else None.

#     For endpoints that are public but need to behave differently for an
#     authenticated caller (e.g. a job detail page that should only reveal an
#     unpublished job to its owning employer or an admin). Never raises —
#     a missing or invalid token just means an anonymous caller.
#     """
#     if not token:
#         return None
#     try:
#         payload = decode_access_token(token)
#     except Exception:
#         return None

#     result = await db.execute(
#         select(User)
#         .options(selectinload(User.organization))
#         .where(User.id == payload.sub)
#     )
#     return result.scalar_one_or_none()


# def require_role(*roles: str):
#     """Dependency factory that restricts access to users with specific roles.

#     Usage::

#         @router.get("/admin", dependencies=[Depends(require_role("ADMIN"))])

#         # or inject the user at the same time:
#         @router.get("/admin")
#         async def admin_route(user: User = Depends(require_role("ADMIN", "EMPLOYER"))):
#             ...

#     Args:
#     ----
#         *roles: One or more role strings that are permitted to access the route.

#     Returns:
#     -------
#         A FastAPI dependency that returns the current user if their role is
#         in the allowed set, or raises ``PermissionDeniedException`` otherwise.

#     """

#     async def _check_role(current_user: User = Depends(get_current_user)) -> User:
#         if current_user.role not in roles:
#             raise PermissionDeniedException()
#         return current_user

#     return _check_role


# def require_org_role(*org_roles: str):
#     """Dependency factory restricting access by organization-level role.

#     Separate axis from `require_role`: `require_role("EMPLOYER")` answers
#     "is this an employer login," this answers "can this specific member
#     act for their organization's billing/team" (OWNER/ADMIN vs MEMBER).
#     Layer both when an endpoint needs both — this only checks
#     `organization_role`, it doesn't imply `role == "EMPLOYER"`.

#     Usage::

#         @router.post("/team/invite")
#         async def invite(user: User = Depends(require_org_role("OWNER", "ADMIN"))):
#             ...
#     """

#     async def _check_org_role(current_user: User = Depends(get_current_user)) -> User:
#         if current_user.organization_role not in org_roles:
#             raise PermissionDeniedException()
#         return current_user

#     return _check_org_role


# async def get_redis_client() -> AsyncGenerator[aioredis.Redis, None]:
#     """Yield a Redis client and ensure it is closed after the request."""
#     redis = aioredis.from_url(settings.redis_url)
#     try:
#         yield redis
#     finally:
#         await redis.aclose()
