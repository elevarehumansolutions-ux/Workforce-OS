"""Tests for AuthService — business logic layer, no HTTP."""

from app.modules.tenancy_identity.enums import MembershipRole
from unittest.mock import MagicMock

import pytest
from fastapi import Response

from app.core.exceptions import (
    AlreadyExistsException,
    InvalidCredentialsException,
    RevokedTokenException
)
from app.modules.auth.service import AuthService

def mock_response() -> Response:
    """Return a mock FastAPI Response object for service tests."""
    return MagicMock(spec=Response)

@pytest.mark.asyncio
async def test_register_returns_auth_response(db_session):
    """Successful registration returns an AuthResponse."""
    from tests.conftest import make_register_data

    service = AuthService(db_session)
    response = await service.register(make_register_data(), mock_response())

    assert response.token_type == "bearer"
    assert response.user.email
    assert response.user.account_status == "pending_verification"
    assert response.user.auth_provider == "password"
    assert response.membership.role == MembershipRole.HR_ADMINISTRATOR.value
    assert response.membership.is_owner is True


@pytest.mark.asyncio
async def test_register_raises_on_duplicate_email(db_session):
    """Registering with an already-taken email raise AlreadyExistsException."""
    from tests.conftest import make_register_data
    service = AuthService(db_session)

    # First registration
    data = make_register_data(email="unique_taken@example.com")
    await service.register(data, mock_response())

    # Second registration — same email
    with pytest.raises(AlreadyExistsException) as exc_info:
        await service.register(
            make_register_data(email="unique_taken@example.com"),
            mock_response(),
        )
    assert "email" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_verify_email_marks_account_verified(db_session):
    """A valid verification token flips the account's status to verified."""
    from tests.conftest import make_register_data
    from app.modules.tenancy_identity.enums import AccountStatus

    service = AuthService(db_session)
    reg = await service.register(make_register_data(), mock_response())
    assert reg.user.account_status == "pending_verification"

    result = await service.verify_email(reg.verification_token)
    assert result.message == "Email verified successfully"

    user = await service._user_service.get_user_by_email(reg.user.email)
    assert user.account_status == AccountStatus.VERIFIED.value


@pytest.mark.asyncio
async def test_verify_email_rejects_unknown_token(db_session):
    """A token that doesn't match any record raises TokenInvalidException."""
    from app.core.exceptions import TokenInvalidException

    service = AuthService(db_session)
    with pytest.raises(TokenInvalidException):
        await service.verify_email("not-a-real-token")


@pytest.mark.asyncio
async def test_verify_email_rejects_reused_token(db_session):
    """A token that's already been consumed raises TokenAlreadyUsedException."""
    from tests.conftest import make_register_data
    from app.core.exceptions import TokenAlreadyUsedException

    service = AuthService(db_session)
    reg = await service.register(make_register_data(), mock_response())

    await service.verify_email(reg.verification_token)

    with pytest.raises(TokenAlreadyUsedException):
        await service.verify_email(reg.verification_token)


@pytest.mark.asyncio
async def test_resend_verification_sends_new_token_and_invalidates_old_one(db_session, monkeypatch):
    """Resending verification issues a new token that works and invalidates the old one (now "already used")."""
    from tests.conftest import make_register_data
    from app.core.exceptions import TokenAlreadyUsedException
    import app.modules.auth.service as auth_service_module

    service = AuthService(db_session)
    reg = await service.register(make_register_data(email="resend_test@example.com"), mock_response())
    old_token = reg.verification_token

    mock_dispatch = MagicMock()
    monkeypatch.setattr(auth_service_module, "dispatch_verification_email", mock_dispatch)

    result = await service.resend_verification_email("resend_test@example.com")
    assert "a new link has been sent" in result.message
    new_token = mock_dispatch.delay.call_args.args[0]
    assert new_token != old_token

    # The new token works (checked first — verify_email's exception path
    # below calls self._db.rollback(), which would otherwise affect this
    # session's later operations if checked afterward instead).
    await service.verify_email(new_token)

    # The old token was invalidated (marked used), not left valid alongside
    # the new one — resend_verification_email -> create_verification_token
    # now calls invalidate_verification_tokens() first (previously a
    # docstring-only claim that the code never actually carried out).
    # invalidate_verification_tokens() marks old rows is_used=True rather
    # than deleting them, so this surfaces as "already used", not "invalid".
    with pytest.raises(TokenAlreadyUsedException):
        await service.verify_email(old_token)


@pytest.mark.asyncio
async def test_resend_verification_silent_for_already_verified_account(db_session, monkeypatch):
    """No new email for an already-verified account.

    Nothing to resend, and the anti-enumeration response stays identical
    either way.
    """
    from tests.conftest import make_register_data
    import app.modules.auth.service as auth_service_module

    service = AuthService(db_session)
    reg = await service.register(make_register_data(email="already_verified@example.com"), mock_response())
    await service.verify_email(reg.verification_token)

    mock_dispatch = MagicMock()
    monkeypatch.setattr(auth_service_module, "dispatch_verification_email", mock_dispatch)

    result = await service.resend_verification_email("already_verified@example.com")
    assert "a new link has been sent" in result.message
    mock_dispatch.delay.assert_not_called()


@pytest.mark.asyncio
async def test_resend_verification_silent_for_unknown_email(db_session, monkeypatch):
    """Resending verification for an unknown email still returns the generic success message, sending nothing."""
    import app.modules.auth.service as auth_service_module

    service = AuthService(db_session)
    mock_dispatch = MagicMock()
    monkeypatch.setattr(auth_service_module, "dispatch_verification_email", mock_dispatch)

    result = await service.resend_verification_email("nobody@example.com")
    assert "a new link has been sent" in result.message
    mock_dispatch.delay.assert_not_called()


@pytest.mark.asyncio
async def test_login_returns_tokens_for_registered_org(db_session):
    """A correct email/password pair returns tokens for the user's org.

    This is also the proof that the memberships RLS bootstrap fix
    (08_DECISIONS.md 2026-09-15) actually works — login queries `memberships`
    before any org context exists, which the original policy would have
    hidden entirely.
    """
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import LoginRequest

    service = AuthService(db_session)
    reg = await service.register(
        make_register_data(email="login_test@example.com"), mock_response()
    )
    await service.verify_email(reg.verification_token)

    login_data = LoginRequest(email="login_test@example.com", password="Password123#")
    response = await service.login(login_data, mock_response())

    assert response.access_token
    assert response.token_type == "bearer"
    assert response.user.email == "login_test@example.com"
    assert response.organization.id == reg.organization.id
    assert response.membership.role == MembershipRole.HR_ADMINISTRATOR.value


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(db_session):
    """Logging in with a correct email but wrong password raises InvalidCredentialsException."""
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import LoginRequest

    service = AuthService(db_session)
    await service.register(make_register_data(email="wrongpass@example.com"), mock_response())

    with pytest.raises(InvalidCredentialsException):
        await service.login(
            LoginRequest(email="wrongpass@example.com", password="WrongPassword123#"),
            mock_response(),
        )


@pytest.mark.asyncio
async def test_login_rejects_unknown_email(db_session):
    """Logging in with an email that has no account raises InvalidCredentialsException."""
    from app.modules.auth.schemas import LoginRequest

    service = AuthService(db_session)
    with pytest.raises(InvalidCredentialsException):
        await service.login(
            LoginRequest(email="nobody@example.com", password="Password123#"),
            mock_response(),
        )


@pytest.mark.asyncio
async def test_refresh_issues_new_access_token(db_session):
    """Refresh returns a new access token and rotates the refresh token, revoking the one just used."""
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import LoginRequest

    service = AuthService(db_session)
    reg = await service.register(make_register_data(email="refresh_test@example.com"), mock_response())
    await service.verify_email(reg.verification_token)

    login_response = mock_response()
    await service.login(
        LoginRequest(email="refresh_test@example.com", password="Password123#"),
        login_response,
    )
    raw_refresh_token = login_response.set_cookie.call_args.kwargs["value"]

    refreshed = await service.refresh(raw_refresh_token, mock_response())

    assert refreshed.token_type == "bearer"
    assert refreshed.access_token

    # Rotation actually happened: the token just used for this refresh is now
    # revoked, so replaying it should fail (access_token has no unique nonce,
    # so two tokens issued with identical claims in the same second can be
    # byte-identical — rotation is what actually proves refresh worked).
    with pytest.raises(RevokedTokenException):
        await service.refresh(raw_refresh_token, mock_response())


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(db_session):
    """Logging out revokes the refresh token, so a subsequent refresh with it raises RevokedTokenException."""
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import LoginRequest

    service = AuthService(db_session)
    reg = await service.register(make_register_data(email="logout_test@example.com"), mock_response())
    await service.verify_email(reg.verification_token)

    login_response = mock_response()
    await service.login(
        LoginRequest(email="logout_test@example.com", password="Password123#"),
        login_response,
    )
    raw_refresh_token = login_response.set_cookie.call_args.kwargs["value"]

    logout_result = await service.logout(raw_refresh_token, mock_response())
    assert logout_result.message == "Logged out successfully"

    with pytest.raises(RevokedTokenException):
        await service.refresh(raw_refresh_token, mock_response())


@pytest.mark.asyncio
async def test_change_password_updates_hash_and_revokes_other_sessions(db_session):
    """Changing password revokes the existing refresh session and makes only the new password work for login."""
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import LoginRequest, ChangePasswordRequest

    service = AuthService(db_session)
    reg = await service.register(make_register_data(email="changepass@example.com"), mock_response())
    await service.verify_email(reg.verification_token)

    login_response = mock_response()
    await service.login(
        LoginRequest(email="changepass@example.com", password="Password123#"),
        login_response,
    )
    raw_refresh_token = login_response.set_cookie.call_args.kwargs["value"]

    user = await service._user_service.get_user_by_email("changepass@example.com")
    result = await service.change_password(
        user,
        ChangePasswordRequest(current_password="Password123#", new_password="NewPassword456#"),
    )
    assert result.message == "Password changed successfully"

    # The session that existed before the password change is now revoked.
    with pytest.raises(RevokedTokenException):
        await service.refresh(raw_refresh_token, mock_response())

    # The new password logs in; the old one no longer does.
    with pytest.raises(InvalidCredentialsException):
        await service.login(
            LoginRequest(email="changepass@example.com", password="Password123#"),
            mock_response(),
        )
    response = await service.login(
        LoginRequest(email="changepass@example.com", password="NewPassword456#"),
        mock_response(),
    )
    assert response.access_token


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current_password(db_session):
    """Changing password with an incorrect current password raises InvalidCredentialsException."""
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import ChangePasswordRequest

    service = AuthService(db_session)
    await service.register(make_register_data(email="changepass2@example.com"), mock_response())
    user = await service._user_service.get_user_by_email("changepass2@example.com")

    with pytest.raises(InvalidCredentialsException):
        await service.change_password(
            user,
            ChangePasswordRequest(current_password="WrongOldPassword1#", new_password="NewPassword456#"),
        )


@pytest.mark.asyncio
async def test_forgot_and_reset_password_flow(db_session, monkeypatch):
    """The forgot-password -> reset-password flow replaces the password, invalidating the old one for login."""
    from tests.conftest import make_register_data
    from app.modules.auth.schemas import LoginRequest
    import app.modules.auth.service as auth_service_module

    service = AuthService(db_session)
    reg = await service.register(make_register_data(email="forgot_test@example.com"), mock_response())
    await service.verify_email(reg.verification_token)

    mock_dispatch = MagicMock()
    monkeypatch.setattr(auth_service_module, "dispatch_password_reset_email", mock_dispatch)

    result = await service.forgot_password("forgot_test@example.com")
    assert "reset link has been sent" in result.message
    raw_token = mock_dispatch.delay.call_args.args[0]

    reset_result = await service.reset_password(raw_token, "BrandNewPass789#")
    assert reset_result.message == "Password reset successfully"

    with pytest.raises(InvalidCredentialsException):
        await service.login(
            LoginRequest(email="forgot_test@example.com", password="Password123#"),
            mock_response(),
        )
    response = await service.login(
        LoginRequest(email="forgot_test@example.com", password="BrandNewPass789#"),
        mock_response(),
    )
    assert response.access_token


@pytest.mark.asyncio
async def test_forgot_password_silent_for_unknown_email(db_session, monkeypatch):
    """Forgot-password for an unknown email still returns the generic success message, sending nothing."""
    import app.modules.auth.service as auth_service_module

    service = AuthService(db_session)
    mock_dispatch = MagicMock()
    monkeypatch.setattr(auth_service_module, "dispatch_password_reset_email", mock_dispatch)

    result = await service.forgot_password("nobody@example.com")
    assert "reset link has been sent" in result.message
    mock_dispatch.delay.assert_not_called()
