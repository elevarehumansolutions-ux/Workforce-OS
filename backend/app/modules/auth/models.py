"""ORM models for the authentication application.

Contains:
- :class:`RefreshToken`: stores a hashed refresh token for auth flows.

Inherits from ``BaseModel`` (which provides ``id``, ``created_at``,
and ``updated_at``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel

if TYPE_CHECKING:
    from app.modules.tenancy_identity.models import User


class RefreshToken(BaseModel):
    """Stores a hashed refresh token used to issue new access tokens."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship resolved at runtime via the model registry — no direct import needed
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class EmailVerificationToken(BaseModel):
    """One-time token sent to a user's email to verify their address."""

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_used: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    # Relationship
    user: Mapped[User] = relationship(
        "User", back_populates="email_verification_tokens"
    )


class PasswordResetToken(BaseModel):
    """One-time token sent to a user's email to authorize a password reset."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_used: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    # Relationship
    user: Mapped[User] = relationship(
        "User", back_populates="password_reset_tokens"
    )
