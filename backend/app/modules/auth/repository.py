""""""
import uuid
from datetime import datetime, UTC

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import EmailVerificationToken, RefreshToken, PasswordResetToken
from app.core.security import hash_token

class AuthRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_verification_token_by_token(self, hashed_token: str) -> EmailVerificationToken | None:
        """Get a verification token record by its hashed value.

        Args:
            hashed_token: The hashed (not raw) verification token.

        Returns:
            The EmailVerificationToken ORM instance if found, None otherwise.
        """
        stmt = select(EmailVerificationToken).where(EmailVerificationToken.token == hashed_token)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_verification_token_by_id(self, token_id: uuid.UUID) -> EmailVerificationToken | None:
        """Get a verification token record by its row id.

        Args:
            token_id: The verification token row's id.

        Returns:
            The EmailVerificationToken ORM instance if found, None otherwise.
        """
        stmt = select(EmailVerificationToken).where(EmailVerificationToken.id == token_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def invalidate_verification_tokens(self, user_id: uuid.UUID):
        """Invalidate an existing token to createa new one"""
        stmt = select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.is_used == False,
        )

        result = await self._db.execute(stmt)
        
        existing_tokens = result.scalars().all()

        for t in existing_tokens:
            t.is_used = True
            self._db.add(t)
            await self._db.flush()

    
    async def create_verification_token(self, user_id: uuid.UUID, hashed_token: str, expires_at: datetime) -> EmailVerificationToken:
        """
        Generate hash and store a new verification email  token for the user.

        Returns:
            The raw (unhashed) token that should be included in the email link
            and later used for verification.
        """
        # Invalidate existing tokens
        await self.invalidate_verification_tokens(user_id)

        # Create new token
        verification_token = EmailVerificationToken(
            user_id=user_id,
            token=hashed_token,
            expires_at=expires_at
        )

        self._db.add(verification_token)
        await self._db.flush()
        await self._db.refresh(verification_token)
        return verification_token
    
    async def create_refresh_token(self, user_id: uuid.UUID, hashed_token: str, expires_at: datetime) -> RefreshToken:
        """Hash and persist a new refresh token for the given user.

        Returns:
            The newly created RefreshToken ORM instance.

        """
        token = RefreshToken(user_id=user_id, token=hashed_token, expires_at=expires_at)
        self._db.add(token)
        await self._db.flush()
        await self._db.refresh(token)

        return token

    async def get_refresh_token(self, raw_token: str):
        """Look up a refresh token record by its raw (unhashed) value.

        Returns:
            The matching RefreshToken, or None if not found.

        """
        hashed_token = hash_token(raw_token)

        stmt = select(RefreshToken).where(RefreshToken.token == hashed_token)
        result = await self._db.execute(stmt)
        return result.scalars().first()
    
    async def mark_verification_token_used(self, token_id: uuid.UUID) -> None:
        """
        Mark Verification token as used.
        """
        token = await self.get_verification_token_by_id(token_id=token_id)
        if token:
            token.is_used = True
            self._db.add(token)
            await self._db.flush()

    async def revoke_refresh_token(self, record: RefreshToken) -> None:
        """Mark a single refresh token record revoked (used by logout/refresh rotation)."""
        record.is_revoked = True
        record.used_at = datetime.now(UTC)
        self._db.add(record)
        await self._db.flush()

    async def revoke_all_refresh_tokens_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every active refresh token for a user (change-password/reset-password
        forces re-login on every other device/session)."""
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        )
        result = await self._db.execute(stmt)
        for token in result.scalars().all():
            token.is_revoked = True
            token.used_at = datetime.now(UTC)
            self._db.add(token)
        await self._db.flush()

    async def get_password_reset_token_by_token(
        self, hashed_token: str
    ) -> PasswordResetToken | None:
        """Get a password reset token record by its hashed value."""
        stmt = select(PasswordResetToken).where(PasswordResetToken.token == hashed_token)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_password_reset_tokens(self, user_id: uuid.UUID) -> None:
        """Invalidate any existing unused password reset tokens before issuing a new one."""
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.is_used == False,
        )
        result = await self._db.execute(stmt)
        for t in result.scalars().all():
            t.is_used = True
            self._db.add(t)
        await self._db.flush()

    async def create_password_reset_token(
        self, user_id: uuid.UUID, hashed_token: str, expires_at: datetime
    ) -> PasswordResetToken:
        """Invalidate any existing tokens, then create and persist a new one."""
        await self.invalidate_password_reset_tokens(user_id)

        reset_token = PasswordResetToken(
            user_id=user_id, token=hashed_token, expires_at=expires_at
        )
        self._db.add(reset_token)
        await self._db.flush()
        await self._db.refresh(reset_token)
        return reset_token

    async def mark_password_reset_token_used(self, token_id: uuid.UUID) -> None:
        """Mark a password reset token as used."""
        stmt = select(PasswordResetToken).where(PasswordResetToken.id == token_id)
        result = await self._db.execute(stmt)
        token = result.scalar_one_or_none()
        if token:
            token.is_used = True
            self._db.add(token)
            await self._db.flush()


