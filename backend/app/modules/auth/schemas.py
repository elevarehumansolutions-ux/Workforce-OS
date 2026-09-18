from pydantic import BaseModel, EmailStr, model_validator, Field
import re
from app.modules.tenancy_identity.schemas import (
    UserResponse,
    OrganizationResponse,
    MembershipResponse,
    MembershipWithOrganizationResponse,
)

def validate_password_strength(v: str) -> str:
    """Validate that a password meets the platform's strength requirements.

    Enforces a minimum length of 8 characters and requires at least one
    uppercase letter, one lowercase letter, one digit, and one special
    character.

    Args:
        v: The plain-text password string to validate.

    Returns:
        The original password string if all checks pass.

    Raises:
        ValueError: If any strength requirement is not met.

    """

    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")

    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one digit")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
        raise ValueError("Password must contain at least one special character")

    return v

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """Payload for creating a new user account.

    Attributes:
        full_name: User's full name, 2–255 characters.
        email: Valid email address; used as the login identifier.
        password: Plain-text password; must pass strength validation.
        confirm_password: Must match ``password`` exactly.

    """
    full_name: str = Field(..., min_length=6, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., exclude=True)
    
    @model_validator(mode="after")
    def password_match(self) -> "RegisterRequest":
        """Ensure ``password`` and ``confirm_password`` are identical.

        Returns:
            The model instance if passwords match.

        Raises:
            ValueError: If the two password fields differ.

        """

        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match!")
        
        return self


class VerifyEmailRequest(BaseModel):
    """Payload for confirming a newly registered account's email address."""

    token: str


class ResendVerificationRequest(BaseModel):
    """Payload for requesting a new verification email.

    Same anti-enumeration shape as ForgotPasswordRequest — the endpoint
    always returns a generic success message regardless of whether the
    email exists or is already verified, so it can't be used to probe
    which addresses are registered.
    """

    email: EmailStr


class AuthResponse(BaseModel):
    """
    Full authentication response returned after register / login.
    """

    user: UserResponse
    organization: OrganizationResponse
    membership: MembershipResponse
    access_token: str
    token_type: str
    verification_token: str | None = None  # Only present in stub / dev mode


class LoginRequest(BaseModel):
    """Payload for logging in.

    No strength validation here, deliberately — this is checking a password
    against a stored hash, not setting a new one. Strength rules only apply
    when a password is being chosen (register / change-password /
    reset-password); applying them here would reject a legitimate existing
    user whose real password doesn't happen to satisfy today's rules.
    """
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Response for a successful token refresh — no user/org/membership payload."""

    access_token: str
    token_type: str


class ChangePasswordRequest(BaseModel):
    """Payload for an authenticated user changing their own password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def check_new_password_strength(self) -> "ChangePasswordRequest":
        """Strength rules apply to the *new* password being chosen, not the old one."""
        validate_password_strength(self.new_password)
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from the current password")
        return self


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting a password reset link."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload for completing a password reset with the emailed token."""

    token: str
    new_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def check_new_password_strength(self) -> "ResetPasswordRequest":
        validate_password_strength(self.new_password)
        return self


class MeResponse(BaseModel):
    """Response for GET /me — the caller's identity plus every organization
    they belong to, for the frontend's org-switcher."""

    user: UserResponse
    memberships: list[MembershipWithOrganizationResponse]


class AcceptInviteRequest(BaseModel):
    """Payload for completing a teammate invite when the invited email has
    no existing account — creates the User and the invited Membership
    together, the same shape as RegisterRequest plus the invite token."""

    token: str
    full_name: str = Field(..., min_length=6, max_length=255)
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., exclude=True)

    @model_validator(mode="after")
    def password_match(self) -> "AcceptInviteRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match!")
        return self
