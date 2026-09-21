"""Pydantic request and response schemas for the authentication app.

Request schemas validate and coerce inbound payloads for registration,
login, token refresh, email verification, and password management flows.

Response schemas define the outbound shapes for auth-related API responses.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
)

from .enums import SubscriptionStatus, AuthProvider, MembershipRole, AccountStatus


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Serialisable representation of a User row returned to the client.

    Sensitive fields (``password_hash``) are intentionally excluded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    auth_provider: AuthProvider
    account_status: AccountStatus
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OrganizationResponse(BaseModel):
    """Serialisable representation of an Organization row returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    subscription_status: SubscriptionStatus
    subscription_expires_at: datetime | None
    fiscal_year_start_month: int
    created_at: datetime
    updated_at: datetime


class MembershipResponse(BaseModel):
    """Serialisable representation of a Membership row returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    organization_id: UUID
    role: MembershipRole
    is_owner: bool
    deactivated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MembershipWithOrganizationResponse(BaseModel):
    """A membership paired with its organization.

    Used by GET /me to render the org-switcher (a user may belong to more
    than one org).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: MembershipRole
    is_owner: bool
    deactivated_at: datetime | None
    organization: OrganizationResponse


class MembershipWithUserResponse(BaseModel):
    """A membership paired with its user.

    Used by the Team Management screen (GET /memberships) to show who each
    membership belongs to.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: MembershipRole
    is_owner: bool
    deactivated_at: datetime | None
    user: UserResponse
    created_at: datetime


class InviteResponse(BaseModel):
    """Serialisable representation of a pending Invite row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: MembershipRole
    expires_at: datetime


class InviteTeammateResponse(BaseModel):
    """Response for POST /memberships.

    Tells the caller whether the teammate was added immediately (already
    had an account) or a pending invite was created and emailed (no account
    yet).
    """

    status: Literal["added", "invited"]
    membership: MembershipWithUserResponse | None = None
    invite: InviteResponse | None = None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class InviteTeammateRequest(BaseModel):
    """Payload for POST /memberships — invite or directly add a teammate."""

    email: EmailStr
    role: MembershipRole


class UpdateMembershipRequest(BaseModel):
    """Payload for PATCH /memberships/{id}.

    Both fields optional and independent: change the role, deactivate/
    reactivate the person's account, or both in one call. At least one must
    be provided.
    """

    role: MembershipRole | None = None
    is_deactivated: bool | None = None

    def has_updates(self) -> bool:
        """Return whether at least one of role or is_deactivated was set."""
        return self.role is not None or self.is_deactivated is not None
