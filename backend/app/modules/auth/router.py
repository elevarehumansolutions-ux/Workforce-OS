"""FastAPI routes for registration, login, and account/session management."""

import logging

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user
from app.core.schemas import MessageResponse
from app.modules.tenancy_identity.models import User
from app.modules.auth.schemas import (
    RegisterRequest,
    AuthResponse,
    VerifyEmailRequest,
    ResendVerificationRequest,
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MeResponse,
    AcceptInviteRequest,
)
from .service import AuthService


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/register", status_code=200)
async def register(
    data: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register a new account and return tokens."""
    service = AuthService(db)
    return await service.register(data, response)


@router.post("/verify-email", status_code=200)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Verify a newly registered account's email address.

    Uses the token from the verification link sent to the user's email.
    """
    service = AuthService(db)
    return await service.verify_email(data.token)


@router.post("/resend-verification", status_code=200)
async def resend_verification(
    data: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Request a new verification email.

    Always returns a generic success message, regardless of whether the
    email exists or is already verified.
    """
    service = AuthService(db)
    return await service.resend_verification_email(data.email)


@router.post("/login", status_code=200)
async def login(
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate by email/password and return tokens."""
    service = AuthService(db)
    return await service.login(data, response)


@router.post("/refresh", status_code=200)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None),
) -> TokenResponse:
    """Issue a new access token from the refresh token cookie."""
    service = AuthService(db)
    return await service.refresh(refresh_token, response)


@router.post("/logout", status_code=200)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None),
) -> MessageResponse:
    """Revoke the current refresh token and clear the cookie."""
    service = AuthService(db)
    return await service.logout(refresh_token, response)


@router.post("/change-password", status_code=200)
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Change the authenticated user's own password."""
    service = AuthService(db)
    return await service.change_password(current_user, data)


@router.post("/forgot-password", status_code=200)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Request a password reset link.

    Always returns a generic success message, regardless of whether the
    email is registered.
    """
    service = AuthService(db)
    return await service.forgot_password(data.email)


@router.post("/reset-password", status_code=200)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Complete a password reset using the token from the reset-password email."""
    service = AuthService(db)
    return await service.reset_password(data.token, data.new_password)


@router.get("/me", status_code=200)
async def me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    """Return the caller's identity plus every organization they belong to.

    Feeds the frontend's org-switcher for multi-membership users.
    """
    service = AuthService(db)
    return await service.get_me(current_user)


@router.post("/accept-invite", status_code=200)
async def accept_invite(
    data: AcceptInviteRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Complete a teammate invite for an email with no prior account.

    Creates the account and logs straight in, same as register().
    """
    service = AuthService(db)
    return await service.accept_invite(data, response)
