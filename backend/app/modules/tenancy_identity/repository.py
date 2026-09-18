""""""

import uuid

from sqlalchemy import select, text

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from .models import User, Organization, Membership, Invite
from app.core.exceptions import UserNotFoundException
from app.core.pagination import paginate
from app.core.schemas import PaginationResponse

class UserRepository:
    def __init__(self, db: AsyncSession):
        self._db = db
    
    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Get user by id.
        """
        stmt = select(User).where(User.id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, email: str) -> User | None:
        """
        Get user by email.
        """
        stmt = select(User).where(User.email == email)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, user: dict) -> User:
        """
        Create a new user.
        """
        new_user = User(**user)
        self._db.add(new_user)
        await self._db.flush()
        await self._db.refresh(new_user)
        return new_user
    
    async def update_account_status(self, user_id: uuid.UUID, status: str) -> User:
        """
        Update a user's account_status. Caller (service layer) commits.
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundException(f"User with id {user_id} not found")
        user.account_status = status
        await self._db.flush()
        return user



class OrganizationRepository:
    def __init__(self, db: AsyncSession):
        self._db = db
    
    async def create_organization(self, organization: dict | None = None) -> Organization:
        """
        Create Organization.
        """
        if organization is None:
            organization = {}

        # `id`'s Python-side default (uuid.uuid4) isn't actually applied
        # until flush — NOT at construction time, despite how it might look.
        # Generating it explicitly here means we know it before INSERT runs,
        # which the next step needs.
        organization.setdefault("id", uuid.uuid4())
        new_organization = Organization(**organization)
        # Setting the org context to that exact id now means the row
        # satisfies the normal (non-bootstrap) branch of both policies by
        # the time we flush.
        #
        # This isn't optional politeness: INSERT ... RETURNING (which the
        # ORM's flush/refresh always uses, to read back server-generated
        # columns like created_at) requires the new row to also satisfy the
        # *read* (USING) policy, not just WITH CHECK — Postgres won't return
        # a row the caller couldn't otherwise SELECT. With no context set,
        # `id = current_org_id` is unknown/false, and the whole INSERT
        # fails with "new row violates row-level security policy", even
        # though WITH CHECK's own bootstrap branch would have allowed the
        # write. The fix isn't a blanket "no context = visible" read
        # exception (that would let any request that forgets to set org
        # context see every organization) — it's establishing the real
        # context, since the id is already known.
        await self._db.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(new_organization.id)},
        )
        self._db.add(new_organization)
        await self._db.flush()
        await self._db.refresh(new_organization)
        return new_organization

    async def get_organization_by_id(self, organization_id: uuid.UUID) -> Organization | None:
        """Get an organization by id. Requires app.current_org_id already
        set to this same id — organizations' RLS policy has no bootstrap
        read exception, only a write one (see RLS_POLICIES_EXPLAINED.md)."""
        stmt = select(Organization).where(Organization.id == organization_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


class MembershipRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_membership(self, membership: dict) -> Membership:
        """
        Create Membership.
        """
        new_membership = Membership(**membership)
        self._db.add(new_membership)
        await self._db.flush()
        await self._db.refresh(new_membership)
        return new_membership

    async def get_user_memberships(self, user_id: uuid.UUID) -> list[Membership]:
        """
        List every membership a user holds, oldest first, with each
        membership's organization eager-loaded (avoids a lazy-load on an
        async session, which would raise MissingGreenlet).
        """
        stmt = (
            select(Membership)
            .options(selectinload(Membership.organization))
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_membership(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Membership | None:
        """
        Get a user's membership in one specific organization, with the
        organization eager-loaded.
        """
        stmt = (
            select(Membership)
            .options(selectinload(Membership.organization))
            .where(
                Membership.user_id == user_id,
                Membership.organization_id == organization_id,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_membership_by_id(self, membership_id: uuid.UUID) -> Membership | None:
        """Get a single membership by its own id, with its user eager-loaded
        (RLS already restricts this to the caller's current org)."""
        stmt = (
            select(Membership)
            .options(selectinload(Membership.user))
            .where(Membership.id == membership_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_org_memberships(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List every membership in one organization (Team Management view),
        oldest first, with each membership's user eager-loaded."""
        stmt = (
            select(Membership)
            .options(selectinload(Membership.user))
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.created_at.asc())
        )
        return await paginate(stmt, page, limit, self._db)

    async def update_membership_role(self, membership: Membership, role: str) -> Membership:
        """Change a membership's role. Caller (service layer) commits."""
        membership.role = role
        await self._db.flush()
        return membership


class InviteRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_pending_invite(self, organization_id: uuid.UUID, email: str) -> Invite | None:
        """Find an existing, not-yet-used invite for this email in this org."""
        stmt = select(Invite).where(
            Invite.organization_id == organization_id,
            Invite.email == email,
            Invite.is_used == False,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_pending_invites(self, organization_id: uuid.UUID, email: str) -> None:
        """Mark any existing pending invite for this email/org as used before
        issuing a new one — same invalidate-before-create pattern as
        EmailVerificationToken/PasswordResetToken."""
        existing = await self.get_pending_invite(organization_id, email)
        if existing:
            existing.is_used = True
            self._db.add(existing)
            await self._db.flush()

    async def create_invite(self, data: dict) -> Invite:
        """Invalidate any existing pending invite for this email/org, then
        create and persist a new one."""
        await self.invalidate_pending_invites(data["organization_id"], data["email"])

        invite = Invite(**data)
        self._db.add(invite)
        await self._db.flush()
        await self._db.refresh(invite)
        return invite

    async def get_invite_by_token(self, hashed_token: str) -> Invite | None:
        """Look up an invite by its hashed token value."""
        stmt = select(Invite).where(Invite.token == hashed_token)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_invite_used(self, invite_id: uuid.UUID) -> None:
        stmt = select(Invite).where(Invite.id == invite_id)
        result = await self._db.execute(stmt)
        invite = result.scalar_one_or_none()
        if invite:
            invite.is_used = True
            self._db.add(invite)
            await self._db.flush()
