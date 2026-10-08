"""Unit tests for the get_current_user dependency.

This is the account-status gate every protected endpoint inherits. Calls it
directly (it's just an async function) rather than through FastAPI's
dependency injection.
"""

import uuid

import pytest

from app.core.dependencies import get_current_user
from app.core.exceptions import (
    AccountBannedException,
    AccountDeactivatedException,
    AccountSuspendedException,
    EmailVerificationRequiredException,
    TokenInvalidException,
    UserNotFoundException,
)
from app.modules.auth.jwt_handler import create_token_pair
from app.modules.tenancy_identity.enums import AccountStatus


def _token_for(user_id) -> str:
    pair = create_token_pair(
        user_id=str(user_id), org_id=str(uuid.uuid4()), role="employee"
    )
    return pair["access_token"]


@pytest.mark.asyncio
async def test_get_current_user_returns_verified_user(db_session):
    """A token for a verified user resolves to that user."""
    from tests.conftest import make_user

    user = make_user(account_status=AccountStatus.VERIFIED.value)
    db_session.add(user)
    await db_session.flush()

    result = await get_current_user(token=_token_for(user.id), db=db_session)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_rejects_pending_verification(db_session):
    """A token for a user whose account is still pending_verification raises EmailVerificationRequiredException."""
    from tests.conftest import make_user

    user = make_user(account_status=AccountStatus.PENDING_VERIFICATION.value)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(EmailVerificationRequiredException):
        await get_current_user(token=_token_for(user.id), db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_suspended(db_session):
    """A token for a suspended user raises AccountSuspendedException."""
    from tests.conftest import make_user

    user = make_user(account_status=AccountStatus.SUSPENDED.value)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountSuspendedException):
        await get_current_user(token=_token_for(user.id), db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_banned(db_session):
    """A token for a banned user raises AccountBannedException."""
    from tests.conftest import make_user

    user = make_user(account_status=AccountStatus.BANNED.value)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountBannedException):
        await get_current_user(token=_token_for(user.id), db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_deactivated(db_session):
    """A token for a deactivated user raises AccountDeactivatedException."""
    from tests.conftest import make_user

    user = make_user(account_status=AccountStatus.DEACTIVATED.value)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountDeactivatedException):
        await get_current_user(token=_token_for(user.id), db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_unknown_user_id(db_session):
    """A token whose subject doesn't match any user raises UserNotFoundException."""
    with pytest.raises(UserNotFoundException):
        await get_current_user(token=_token_for(uuid.uuid4()), db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_garbage_token(db_session):
    """A malformed, non-JWT token string raises TokenInvalidException."""
    with pytest.raises(TokenInvalidException):
        await get_current_user(token="not-a-real-jwt", db=db_session)
