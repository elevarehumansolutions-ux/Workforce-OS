"""Business logic for registration, login, session, and password flows."""
import logging
import uuid

from datetime import datetime, timezone, UTC, timedelta

from fastapi import Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .security import hash_password, verify_password
from app.core.security import generate_token, hash_token
from app.core.schemas import MessageResponse
from app.modules.tenancy_identity.service import UserService, OrganizationService, MembershipService
from app.modules.tenancy_identity.schemas import (
    UserResponse,
    OrganizationResponse,
    MembershipResponse,
)
from app.modules.auth.schemas import (
    RegisterRequest,
    AuthResponse,
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    MeResponse,
    AcceptInviteRequest,
)
from app.modules.tenancy_identity.schemas import MembershipWithOrganizationResponse
from app.modules.tenancy_identity.models import User, Organization, Membership
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.enums import AccountStatus
from app.modules.auth.jwt_handler import create_token_pair, decode_refresh_token
from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsException,
    TokenInvalidException,
    TokenAlreadyUsedException,
    VerificationTokenExpiredException,
    InternalServerErrorException,
    InvalidCredentialsException,
    RefreshTokenMissing,
    RevokedTokenException,
    TokenExpiredException,
    UserNotFoundException,
    EmailVerificationRequiredException,
    AccountSuspendedException,
    AccountBannedException,
    AccountDeactivatedException,
    NoActiveMembershipException,
)
from app.modules.auth.repository import AuthRepository
from .tasks import dispatch_verification_email, dispatch_password_reset_email

logger = logging.getLogger(__name__)


class AuthService:
    """Coordinates registration, authentication, and session/token lifecycle."""

    def __init__(self, db: AsyncSession):
        """Initialize the service and its collaborating services/repository."""
        self._db = db
        self._user_service = UserService(db)
        self._org_service = OrganizationService(db)
        self._membership_service = MembershipService(db)
        self._auth_repo = AuthRepository(db)
    
    @staticmethod
    def _build_user_response(user: User) -> UserResponse:
        """Convert a ``User`` ORM instance into a ``UserResponse`` schema.

        Strips sensitive fields (e.g. ``password_hash``) and coerces enum
        strings back to their enum members for clean serialisation.

        Args:
            user: The ``User`` ORM object freshly fetched or flushed from the
                  database session.

        Returns:
            A ``UserResponse`` Pydantic model populated from the ORM row.

        """
        return UserResponse.model_validate(user)

    @staticmethod
    def _build_organization_response(org: Organization) -> OrganizationResponse:
        """Convert an ``Organization`` ORM instance into an ``OrganizationResponse``.

        Args:
            org: The ``Organization`` ORM object freshly fetched or flushed
                 from the database session.

        Returns:
            An ``OrganizationResponse`` Pydantic model populated from the ORM row.

        """
        return OrganizationResponse.model_validate(org)

    @staticmethod
    def _build_membership_response(mem: Membership) -> MembershipResponse:
        """Convert a ``Membership`` ORM instance into a ``MembershipResponse``.

        Args:
            mem: The ``Membership`` ORM object freshly fetched or flushed from
                 the database session.

        Returns:
            A ``MembershipResponse`` Pydantic model populated from the ORM row.

        """
        return MembershipResponse.model_validate(mem)
    
    async def create_verification_token(self, user_id: uuid.UUID) -> str:
        """Generate hash and store a new verification email  token for the user.

        Invalidates any existing unused tokens before creating the new one.

        Returns:
            The raw (unhashed) token that should be included in the email link
            and later used for verification.
        """
        raw_token = generate_token()
        hashed_token = hash_token(raw_token)

        # AuthRepository.create_verification_token() already invalidates any
        # existing unused tokens for this user before creating the new one —
        # no separate call needed here.
        await self._auth_repo.create_verification_token(
            user_id,
            hashed_token,
            datetime.now(UTC)
            + timedelta(hours=settings.email_verification_token_expiry),
        )
        await self._db.commit()
        return raw_token
    
    async def get_verification_token(self, raw_token: str):
        """Look up and validate a verification token by its raw value."""
        hashed = hash_token(raw_token)
        token_record = await self._auth_repo.get_verification_token_by_token(hashed)
        if not token_record:
            raise TokenInvalidException()

        if token_record.is_used:
            raise TokenAlreadyUsedException()

        if token_record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise VerificationTokenExpiredException()

        return token_record
    
    async def register(self, data: RegisterRequest, response: Response) -> AuthResponse:
        """Register a new account and return tokens."""
        # Check if email exists in the database
        user = await self._user_service.get_user_by_email(data.email)
        if user:
            raise AlreadyExistsException(message="Email address already exist")
        
        try:
            # Hash Password and build user data
            user = await self._user_service.create_user(
                {
                    "email": data.email,
                    "full_name": data.full_name,
                    "password_hash": hash_password(data.password),
                    "last_login_at": datetime.now(timezone.utc),
                }
            )
            # Create Organization with null values initially to get the id values first and during onboarding, an update can be done
            org = await self._org_service.create_organization()

            # Whoever registers is the founding Owner (08_DECISIONS.md 2026-09-13):
            # is_owner=True and role are passed explicitly here, never as column
            # defaults — every other caller of create_membership (e.g. Invite
            # Teammate) must decide both for itself, not inherit registration's
            # values by accident.
            mem = await self._membership_service.create_membership(
                {
                    "user_id": user.id,
                    "organization_id": org.id,
                    "role": MembershipRole.HR_ADMINISTRATOR.value,
                    "is_owner": True,
                }
            )

            logger.info(
                "User registered successfully:\n"
                f"Email: {user.email}\n"
                f"Organization ID: {org.id}\n"
                f"Membership ID: {mem.id}\n"
            )

            # Generate token and dispatch email with the token
            verification_token = await self.create_verification_token(user.id)
            next_url = f"/employer/organization/onboarding?token={verification_token}"
            dispatch_verification_email.delay(verification_token, user.email, next_url)

            token_pair = create_token_pair(
                user_id=user.id,
                org_id=org.id,
                role=mem.role
            )

            # Set access token in cookie
            response.set_cookie(
                key="refresh_token",
                value=token_pair["refresh_token"],
                httponly=True,
                secure=settings.environment == "production",
                samesite="lax",
                max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60
            )
        

            # Store refresh Token
            await self._auth_repo.create_refresh_token(
                user_id=user.id,
                hashed_token=hash_token(token_pair["refresh_token"]),
                expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
            )
        except IntegrityError:
            # A second registration for the same email landed between the
            # get_user_by_email check above and this insert — the DB's own
            # unique constraint is the real guarantee, the check above is
            # just the fast path. Anything else (a genuinely unexpected DB
            # error) propagates to the global handler as a 500, rather than
            # being reported to the client as a fabricated 400.
            await self._db.rollback()
            raise AlreadyExistsException(message="Email address already exist")

        # Explicitly commit everything
        await self._db.commit()
        
        return AuthResponse(
            user=self._build_user_response(user),
            organization=self._build_organization_response(org),
            membership=self._build_membership_response(mem),
            access_token=token_pair["access_token"],
            token_type=token_pair["token_type"],
            verification_token=verification_token if settings.email_stub_mode else None,
        )
    
    async def verify_email(self, token: str) -> MessageResponse:
        """Verify a user's email using the raw token from the verification link.

        Args:
            token: The raw (unhashed) token from the verification link.

        Returns:
            A ``MessageResponse`` Pydantic model indicating success.

        Raises:
            TokenInvalidException:
                If no valid verification token record is found.
            TokenAlreadyUsedException:
                If the verification token has already been used.
            VerificationTokenExpiredException:
                If the verification token has expired.
            InternalServerErrorException:
                If an unexpected database error occurs.
        """
        try:
            # 1) Look up the token (raises exception on missing/invalid)
            token_record = await self.get_verification_token(token)

            # 2) Mark as used and update user's account status to verified
            await self._auth_repo.mark_verification_token_used(
                token_record.id,
            )
            await self._user_service.update_account_status(
                token_record.user_id,
                AccountStatus.VERIFIED.value,
            )

            # 3) Commit the changes to the DB
            await self._db.commit()

            # 4) Return a success message
            return MessageResponse(message="Email verified successfully")

        except (TokenInvalidException, TokenAlreadyUsedException, VerificationTokenExpiredException):
            # These are expected failures — let them propagate up to the endpoint
            await self._db.rollback()
            raise
        except Exception as e:
            # Unexpected DB errors: rollback and wrap in an internal error
            await self._db.rollback()
            raise InternalServerErrorException(f"Verification error: {e}")

    async def resend_verification_email(self, email: str) -> MessageResponse:
        """Send a new verification email, replacing any still-unused one.

        Always returns the same generic message regardless of whether the
        email exists or is already verified — same anti-enumeration
        reasoning as forgot_password. Only sends anything for an account
        genuinely stuck in PENDING_VERIFICATION.
        """
        user = await self._user_service.get_user_by_email(email)
        if user and user.account_status == AccountStatus.PENDING_VERIFICATION.value:
            verification_token = await self.create_verification_token(user.id)
            next_url = f"/employer/organization/onboarding?token={verification_token}"
            dispatch_verification_email.delay(verification_token, user.email, next_url)

        return MessageResponse(
            message="If an account with that email needs verifying, a new link has been sent."
        )

    async def login(self, data: LoginRequest, response: Response) -> AuthResponse:
        """Authenticate by email/password and return tokens for one of the user's orgs.

        Which org: the earliest-joined membership is the login-time default
        (08_DECISIONS.md 2026-09-15) — the frontend org-switcher (M2) is how
        a multi-membership user picks a different one afterward.
        """
        user = await self._user_service.get_user_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            # Same error either way — never reveal whether the email exists.
            raise InvalidCredentialsException()

        # Same account-status gate as get_current_user (core/dependencies.py)
        # — without this, a deactivated/banned/suspended account could still
        # log in and receive a valid token; it would only fail on the *next*
        # request, which is confusing and lets a token exist for an account
        # that should never have gotten one.
        if user.account_status == AccountStatus.PENDING_VERIFICATION.value:
            raise EmailVerificationRequiredException()
        if user.account_status == AccountStatus.SUSPENDED.value:
            raise AccountSuspendedException()
        if user.account_status == AccountStatus.BANNED.value:
            raise AccountBannedException()
        if user.account_status == AccountStatus.DEACTIVATED.value:
            raise AccountDeactivatedException()

        # Bootstrap exception: no org context exists yet at login — that's
        # what we're about to determine — so identify the session by user id
        # instead. The memberships RLS policy only lets a no-org-context
        # session see its own rows this way (docs/RLS_POLICIES_EXPLAINED.md).
        # app.current_org_id is explicitly cleared first, not just assumed
        # unset: normally true (each request gets a fresh transaction, and
        # SET LOCAL's scope ends with it), but relying on that as an
        # unenforced assumption rather than a guarantee is exactly the kind
        # of gap that showed up once a connection legitimately gets reused
        # across more than one logical unit of work — enforce it here
        # instead of trusting it (08_DECISIONS.md 2026-09-18).
        await self._db.execute(text("SELECT set_config('app.current_org_id', '', true)"))
        await self._db.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user.id)},
        )
        memberships = await self._membership_service.get_user_memberships(user.id)
        # Deactivation is scoped to one membership (08_DECISIONS.md
        # 2026-09-18), not the whole account — a user deactivated from one
        # org can still log in and land in any other org they're still
        # active in. get_user_memberships() itself still returns every
        # membership (deactivated included), so GET /me's org-switcher can
        # show "removed from X" rather than silently hiding it.
        active_memberships = [m for m in memberships if m.deactivated_at is None]
        if not active_memberships:
            raise NoActiveMembershipException()

        membership = active_memberships[0]

        # membership.organization_id is a plain column on a row that already
        # passed memberships' own (bootstrap-exempt) RLS check above — no
        # organizations-table read permission needed to read it. The eager
        # load inside get_user_memberships() ran under blank org context, so
        # it doesn't have organizations' row: organizations' own read policy
        # has no bootstrap exception (docs/RLS_POLICIES_EXPLAINED.md), only
        # memberships' does. Set the real org context now, using that column
        # value, then fetch the organization fresh — it will actually be
        # visible now that context matches it.
        await self._db.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(membership.organization_id)},
        )
        org = await self._org_service.get_organization_by_id(membership.organization_id)

        user.last_login_at = datetime.now(timezone.utc)

        token_pair = create_token_pair(
            user_id=user.id,
            org_id=str(org.id),
            role=membership.role,
        )

        response.set_cookie(
            key="refresh_token",
            value=token_pair["refresh_token"],
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
            max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        )

        await self._auth_repo.create_refresh_token(
            user_id=user.id,
            hashed_token=hash_token(token_pair["refresh_token"]),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )

        await self._db.commit()
        # `user.last_login_at` was just set, which flushed an UPDATE and left
        # `updated_at` (server-side onupdate=func.now()) expired — refresh so
        # Pydantic's synchronous model_validate below doesn't hit a lazy
        # async load (MissingGreenlet).
        await self._db.refresh(user)

        return AuthResponse(
            user=self._build_user_response(user),
            organization=self._build_organization_response(org),
            membership=self._build_membership_response(membership),
            access_token=token_pair["access_token"],
            token_type=token_pair["token_type"],
        )

    async def refresh(self, raw_refresh_token: str | None, response: Response) -> TokenResponse:
        """Issue a new access token from a valid, non-revoked refresh token.

        Rotates the refresh token (old one revoked, new one issued) and
        re-validates that the membership it was issued for still exists —
        a role change or removal since the token was issued is picked up
        here, not silently carried forward ("refresh re-validates live
        membership", 10_CURRENT_TASK.md).
        """
        if not raw_refresh_token:
            raise RefreshTokenMissing()

        payload = decode_refresh_token(raw_refresh_token)

        record = await self._auth_repo.get_refresh_token(raw_refresh_token)
        if record is None:
            raise TokenInvalidException()
        if record.is_revoked:
            raise RevokedTokenException()
        if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise TokenExpiredException()

        # Refresh already knows which org it's acting for (the token's own
        # signature-verified claim), unlike login — so it establishes org
        # context directly rather than needing login's user-scoped exception.
        await self._db.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": payload.org_id},
        )
        membership = await self._membership_service.get_membership(
            uuid.UUID(payload.sub), uuid.UUID(payload.org_id)
        )
        # Same rule as get_current_membership (core/dependencies.py): a
        # deactivated membership can't be refreshed into a new token, even
        # though it's scoped to this one org, not the user globally.
        if membership is None or membership.deactivated_at is not None:
            raise InvalidCredentialsException("Membership no longer exists")

        await self._auth_repo.revoke_refresh_token(record)

        token_pair = create_token_pair(
            user_id=payload.sub,
            org_id=payload.org_id,
            role=membership.role,
        )

        response.set_cookie(
            key="refresh_token",
            value=token_pair["refresh_token"],
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
            max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        )

        await self._auth_repo.create_refresh_token(
            user_id=uuid.UUID(payload.sub),
            hashed_token=hash_token(token_pair["refresh_token"]),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )

        await self._db.commit()

        return TokenResponse(
            access_token=token_pair["access_token"],
            token_type=token_pair["token_type"],
        )

    async def logout(self, raw_refresh_token: str | None, response: Response) -> MessageResponse:
        """Revoke the current refresh token (if any) and clear the cookie.

        Lenient by design: a missing or already-revoked token still returns
        success — logging out shouldn't be something a client can get wrong.
        """
        if raw_refresh_token:
            record = await self._auth_repo.get_refresh_token(raw_refresh_token)
            if record and not record.is_revoked:
                await self._auth_repo.revoke_refresh_token(record)
                await self._db.commit()

        response.delete_cookie("refresh_token")
        return MessageResponse(message="Logged out successfully")

    async def change_password(self, user: User, data: ChangePasswordRequest) -> MessageResponse:
        """Change an authenticated user's own password.

        Revokes every other refresh token for this user — a changed password
        should end every other session, not just leave them running.
        """
        if not verify_password(data.current_password, user.password_hash):
            raise InvalidCredentialsException("Current password is incorrect")

        user.password_hash = hash_password(data.new_password)

        await self._auth_repo.revoke_all_refresh_tokens_for_user(user.id)

        await self._db.commit()
        return MessageResponse(message="Password changed successfully")

    async def forgot_password(self, email: str) -> MessageResponse:
        """Request a password reset link.

        Always returns the same generic message regardless of whether the
        email exists — this prevents the endpoint being used to discover
        which emails are registered.
        """
        user = await self._user_service.get_user_by_email(email)
        if user:
            raw_token = generate_token()
            hashed_token = hash_token(raw_token)
            await self._auth_repo.create_password_reset_token(
                user.id,
                hashed_token,
                datetime.now(UTC) + timedelta(hours=settings.password_reset_token_expiry),
            )
            await self._db.commit()
            dispatch_password_reset_email.delay(raw_token, user.email)

        return MessageResponse(
            message="If an account with that email exists, a password reset link has been sent."
        )

    async def reset_password(self, raw_token: str, new_password: str) -> MessageResponse:
        """Complete a password reset using the emailed token.

        Also revokes every existing refresh token — the whole point of a
        password reset is usually "I think someone else has access," so
        every existing session should end, not just the one doing the reset.
        """
        hashed = hash_token(raw_token)
        token_record = await self._auth_repo.get_password_reset_token_by_token(hashed)
        if not token_record:
            raise TokenInvalidException()
        if token_record.is_used:
            raise TokenAlreadyUsedException()
        if token_record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise VerificationTokenExpiredException()

        user = await self._user_service.get_user_by_id(token_record.user_id)
        if not user:
            raise UserNotFoundException()

        user.password_hash = hash_password(new_password)
        await self._auth_repo.mark_password_reset_token_used(token_record.id)
        await self._auth_repo.revoke_all_refresh_tokens_for_user(user.id)

        await self._db.commit()
        return MessageResponse(message="Password reset successfully")

    async def get_me(self, user: User) -> MeResponse:
        """Return the caller's identity plus every org they belong to.

        Same bootstrap exception as login (no org chosen yet, identify by
        user id instead), reused here for the org-switcher's benefit.
        """
        # Same explicit reset as login(), same reasoning — see its comment.
        await self._db.execute(text("SELECT set_config('app.current_org_id', '', true)"))
        await self._db.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user.id)},
        )
        memberships = await self._membership_service.get_user_memberships(user.id)

        return MeResponse(
            user=self._build_user_response(user),
            memberships=[
                MembershipWithOrganizationResponse.model_validate(m) for m in memberships
            ],
        )

    async def accept_invite(self, data: AcceptInviteRequest, response: Response) -> AuthResponse:
        """Complete a teammate invite for an email with no prior account.

        Creates the User and the invited Membership together, then logs
        them straight in (same shape as register()).
        """
        hashed = hash_token(data.token)
        invite = await self._membership_service.get_invite_by_token(hashed)
        if not invite:
            raise TokenInvalidException()
        if invite.is_used:
            raise TokenAlreadyUsedException()
        if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise VerificationTokenExpiredException()

        # Safety net: someone could have registered separately with this
        # email between the invite being sent and accepted.
        existing = await self._user_service.get_user_by_email(invite.email)
        if existing:
            raise AlreadyExistsException(
                message="An account with this email already exists — log in and ask to be added instead"
            )

        # Establish org context from the invite row (no RLS on `invites`,
        # but it's our own already-validated record) — same pattern as
        # refresh() trusting the org id embedded in a validated JWT, just a
        # validated Invite row here instead of a token.
        await self._db.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(invite.organization_id)},
        )

        user = await self._user_service.create_user({
            "email": invite.email,
            "full_name": data.full_name,
            "password_hash": hash_password(data.password),
            "last_login_at": datetime.now(timezone.utc),
            # The invite email proves ownership already — no separate
            # verify-email step needed for an invited teammate.
            "account_status": AccountStatus.VERIFIED.value,
        })

        membership = await self._membership_service.create_membership({
            "user_id": user.id,
            "organization_id": invite.organization_id,
            "role": invite.role,
            "is_owner": False,
        })

        org = await self._org_service.get_organization_by_id(invite.organization_id)

        await self._membership_service.mark_invite_used(invite.id)

        token_pair = create_token_pair(
            user_id=user.id,
            org_id=invite.organization_id,
            role=membership.role,
        )

        response.set_cookie(
            key="refresh_token",
            value=token_pair["refresh_token"],
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
            max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        )

        await self._auth_repo.create_refresh_token(
            user_id=user.id,
            hashed_token=hash_token(token_pair["refresh_token"]),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )

        await self._db.commit()

        return AuthResponse(
            user=self._build_user_response(user),
            organization=self._build_organization_response(org),
            membership=self._build_membership_response(membership),
            access_token=token_pair["access_token"],
            token_type=token_pair["token_type"],
        )
