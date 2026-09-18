"""ORM models for Cluster 1: Tenancy & Identity (organizations, users, memberships)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import uuid

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import CheckConstraint, Integer, String, DateTime, Uuid, Boolean, ForeignKey, UniqueConstraint

from app.core.database import BaseModel
from .enums import SubscriptionStatus, AuthProvider, MembershipRole, AccountStatus

if TYPE_CHECKING:
    from app.modules.auth.models import EmailVerificationToken, RefreshToken, PasswordResetToken


class Organization(BaseModel):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            'fiscal_year_start_month BETWEEN 1 AND 12',
            name='check_fiscal_year_start_month'
        ),
        CheckConstraint(
            f"subscription_status IN {tuple(s.value for s in SubscriptionStatus)}",
            name='check_subscription_status'
        ),
    )


    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        String(50),
        nullable=False,
        default=SubscriptionStatus.TRIAL.value,
        server_default=SubscriptionStatus.TRIAL.value
    )
    subscription_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    fiscal_year_start_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    # Relationships
    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"account_status IN {tuple(s.value for s in AccountStatus)}",
            name='check_account_status'
        ),
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    auth_provider: Mapped[AuthProvider] = mapped_column(
        String(30),
        nullable=False,
        default=AuthProvider.PASSWORD.value,
        server_default=AuthProvider.PASSWORD.value
    )
    # account_status is the single source of truth for account state
    # (pending_verification/verified/suspended/deactivated/banned) — no
    # separate is_active/is_verified booleans, so there's exactly one place
    # to check or update, not several that can drift out of sync.
    account_status: Mapped[AccountStatus] = mapped_column(
        String(50),
        nullable=False,
        default=AccountStatus.PENDING_VERIFICATION.value,
        server_default=AccountStatus.PENDING_VERIFICATION.value
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
    )
    email_verification_tokens: Mapped[list[EmailVerificationToken]] = relationship(
        "EmailVerificationToken", back_populates="user"
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        "PasswordResetToken", back_populates="user"
    )


class Membership(BaseModel):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            'organization_id',
            'user_id',
            name='uq_memberships_organization_user'
        ),
        CheckConstraint(
            f"role IN {tuple(r.value for r in MembershipRole)}",
            name='check_membership_role'
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('organizations.id'),
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id'),
        nullable=False
    )
    # No default — 04_DATABASE.md gives this column no DEFAULT clause, and
    # there's no "safe" role to fall back to the way is_owner falls back to
    # False. Every caller must decide the role explicitly.
    role: Mapped[MembershipRole] = mapped_column(
        String(50),
        nullable=False,
    )
    is_owner: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default='false'
    )
    # Scoped to this one organization, not the person globally (08_DECISIONS.md
    # 2026-09-18) — deactivating someone from Org A must not lock them out of
    # Org B if they belong to both. NULL = active. Deliberately not reusing
    # the deleted_at soft-delete convention: a deactivated membership is
    # still a real, current row (still listed in Team Management, still
    # shows in the org-switcher as "deactivated"), not a row standing in for
    # something that used to exist.
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="memberships")
    organization: Mapped["Organization"] = relationship(back_populates="memberships")


class Invite(BaseModel):
    """A pending invite to join an organization — for an email address that
    doesn't have a User account yet. No RLS: looked up by its own random
    token before any org/user context exists, same reasoning as
    EmailVerificationToken/PasswordResetToken/RefreshToken (auth/models.py).
    When the invited email already has an account, no Invite row is ever
    created — the Membership is added directly instead (see
    tenancy_identity/service.py InviteService.invite_teammate).
    """

    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(
            f"role IN {tuple(r.value for r in MembershipRole)}",
            name='check_invite_role'
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[MembershipRole] = mapped_column(String(50), nullable=False)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey('users.id'), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
