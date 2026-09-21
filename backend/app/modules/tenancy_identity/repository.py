"""Data-access layer for the tenancy_identity module.

Provides CRUD and lookup operations for users, organizations, memberships,
and invites. Repositories flush (never commit) — commits are the service/
router layer's responsibility.
"""

import uuid

from sqlalchemy import select, text

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from .models import User, Organization, Membership, Invite
from app.core.exceptions import UserNotFoundException
from app.core.pagination import paginate
from app.core.schemas import PaginationResponse

class UserRepository:
    """Handles persistence and lookups for users."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an async session."""
        self._db = db

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get a user by id.

        Args:
            user_id: Id of the user to fetch.

        Returns:
            The matching ``User``, or ``None`` if not found.
        """
        stmt = select(User).where(User.id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email address.

        Args:
            email: Email address to look up.

        Returns:
            The matching ``User``, or ``None`` if not found.
        """
        stmt = select(User).where(User.email == email)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, user: dict) -> User:
        """Insert a new user, flush, and refresh it from the database.

        Args:
            user: Field values for the new ``User`` row.

        Returns:
            The newly created and refreshed ``User``.
        """
        new_user = User(**user)
        self._db.add(new_user)
        await self._db.flush()
        await self._db.refresh(new_user)
        return new_user

    async def update_account_status(self, user_id: uuid.UUID, status: str) -> User:
        """Update a user's account_status. Caller (service layer) commits.

        Args:
            user_id: Id of the user to update.
            status: New ``AccountStatus`` value to set.

        Returns:
            The updated ``User``.

        Raises:
            UserNotFoundException: If no user with that id exists.
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundException(f"User with id {user_id} not found")
        user.account_status = status
        await self._db.flush()
        return user



class OrganizationRepository:
    """Handles persistence and lookups for organizations."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an async session."""
        self._db = db

    async def create_organization(self, organization: dict | None = None) -> Organization:
        """Insert a new organization, flush, and refresh it from the database.

        Explicitly generates the row's id before INSERT and sets
        ``app.current_org_id`` to it so the new row satisfies both the RLS
        write (``WITH CHECK``) and read (``USING``) policies during the
        flush/refresh's ``INSERT ... RETURNING``.

        Args:
            organization: Field values for the new organization. Defaults to
                an empty dict, creating an organization with only defaults.

        Returns:
            The newly created and refreshed ``Organization``.
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
        """Get an organization by id.

        Requires ``app.current_org_id`` already set to this same id —
        organizations' RLS policy has no bootstrap read exception, only a
        write one (see RLS_POLICIES_EXPLAINED.md).

        Args:
            organization_id: Id of the organization to fetch.

        Returns:
            The matching ``Organization``, or ``None`` if not found or not
            visible under the current RLS context.
        """
        stmt = select(Organization).where(Organization.id == organization_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_organization(self, organization: Organization, data: dict) -> Organization:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            organization: The ``Organization`` instance to update.
            data: Mapping of field names to their new values.
        
        Returns:
            The updated and refreshed ``Organization``
        """

        for field, value in data.items():
            setattr(organization, field, value)
        
        await self._db.flush()
        await self._db.refresh(organization)
        return organization


class MembershipRepository:
    """Handles persistence and lookups for memberships."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an async session."""
        self._db = db

    async def create_membership(self, membership: dict) -> Membership:
        """Insert a new membership, flush, and refresh it from the database.

        Args:
            membership: Field values for the new ``Membership`` row.

        Returns:
            The newly created and refreshed ``Membership``.
        """
        new_membership = Membership(**membership)
        self._db.add(new_membership)
        await self._db.flush()
        await self._db.refresh(new_membership)
        return new_membership

    async def get_user_memberships(self, user_id: uuid.UUID) -> list[Membership]:
        """List every membership a user holds, oldest first.

        Each membership's organization is eager-loaded (avoids a lazy-load
        on an async session, which would raise MissingGreenlet).

        Args:
            user_id: Id of the user to list memberships for.

        Returns:
            The user's memberships, ordered by creation time ascending.
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
        """Get a user's membership in one specific organization.

        The organization is eager-loaded.

        Args:
            user_id: Id of the user.
            organization_id: Id of the organization.

        Returns:
            The matching ``Membership``, or ``None`` if not found.
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
        """Get a single membership by its own id, with its user eager-loaded.

        RLS already restricts this to the caller's current org.

        Args:
            membership_id: Id of the membership to fetch.

        Returns:
            The matching ``Membership``, or ``None`` if not found.
        """
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
        """List every membership in one organization (Team Management view).

        Ordered oldest first, with each membership's user eager-loaded.

        Args:
            organization_id: Organization to list memberships for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Membership`` rows.
        """
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
    """Handles persistence and lookups for pending organization invites."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an async session."""
        self._db = db

    async def get_pending_invite(self, organization_id: uuid.UUID, email: str) -> Invite | None:
        """Find an existing, not-yet-used invite for this email in this org."""
        stmt = select(Invite).where(
            Invite.organization_id == organization_id,
            Invite.email == email,
            Invite.is_used.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_pending_invites(self, organization_id: uuid.UUID, email: str) -> None:
        """Mark any existing pending invite for this email/org as used.

        Run before issuing a new one — same invalidate-before-create pattern
        as EmailVerificationToken/PasswordResetToken.

        Args:
            organization_id: Organization the invite belongs to.
            email: Invited email address.
        """
        existing = await self.get_pending_invite(organization_id, email)
        if existing:
            existing.is_used = True
            self._db.add(existing)
            await self._db.flush()

    async def create_invite(self, data: dict) -> Invite:
        """Invalidate any existing pending invite for this email/org, then create a new one.

        Args:
            data: Field values for the new ``Invite`` row. Must include
                ``organization_id`` and ``email``.

        Returns:
            The newly created and refreshed ``Invite``.
        """
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
        """Mark an invite as used, if it still exists.

        Args:
            invite_id: Id of the invite to mark used. Silently a no-op if
                no invite with that id exists.
        """
        stmt = select(Invite).where(Invite.id == invite_id)
        result = await self._db.execute(stmt)
        invite = result.scalar_one_or_none()
        if invite:
            invite.is_used = True
            self._db.add(invite)
            await self._db.flush()
