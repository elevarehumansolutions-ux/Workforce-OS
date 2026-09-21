"""Business logic for the tenancy_identity module.

Thin service layer over UserRepository/OrganizationRepository/
MembershipRepository/InviteRepository: most methods simply delegate, with
richer logic (guardrails, invite-vs-membership branching) in
MembershipService.update_membership and .invite_teammate.
"""

from datetime import UTC, datetime, timedelta

from .repository import UserRepository, OrganizationRepository, MembershipRepository, InviteRepository
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, Organization, Membership, Invite
from app.core.security import generate_token, hash_token
from app.core.config import settings


class UserService:
    """Business logic for creating and looking up users."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its repository."""
        self._db = db
        self._repo = UserRepository(db)

    async def get_user_by_email(self, email: str) -> User:
        """Fetch a user by email address.

        Args:
            email: Email address to look up.

        Returns:
            The matching ``User``, or ``None`` if not found.
        """
        return await self._repo.get_user_by_email(email)

    async def get_user_by_id(self, user_id) -> User | None:
        """Fetch a user by id.

        Args:
            user_id: Id of the user to fetch.

        Returns:
            The matching ``User``, or ``None`` if not found.
        """
        return await self._repo.get_user_by_id(user_id)

    async def create_user(self, user: dict) -> User:
        """Create a new user.

        Args:
            user: Field values for the new user.

        Returns:
            The newly created ``User``.
        """
        return await self._repo.create_user(user)

    async def update_account_status(self, user_id, status: str) -> User:
        """Update a user's account status.

        Args:
            user_id: Id of the user to update.
            status: New ``AccountStatus`` value to set.

        Returns:
            The updated ``User``.

        Raises:
            UserNotFoundException: If no user with that id exists.
        """
        return await self._repo.update_account_status(user_id, status)


class OrganizationService:
    """Business logic for creating and looking up organizations."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its repository."""
        self._db = db
        self._repo = OrganizationRepository(db)

    async def create_organization(self, organization: dict | None = None) -> Organization:
        """Create a new organization.

        Args:
            organization: Field values for the new organization. Defaults
                to an empty dict, creating an organization with only
                defaults.

        Returns:
            The newly created ``Organization``.
        """
        return await self._repo.create_organization(organization)

    async def get_organization_by_id(self, organization_id) -> Organization | None:
        """Fetch an organization by id.

        Args:
            organization_id: Id of the organization to fetch.

        Returns:
            The matching ``Organization``, or ``None`` if not found or not
            visible under the current RLS context.
        """
        return await self._repo.get_organization_by_id(organization_id)


class MembershipService:
    """Business logic for memberships and organization invites."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its repositories."""
        self._db = db
        self._repo = MembershipRepository(db)
        self._user_repo = UserRepository(db)
        self._invite_repo = InviteRepository(db)

    async def create_membership(self, membership: dict) -> Membership:
        """Create a new membership.

        Args:
            membership: Field values for the new membership.

        Returns:
            The newly created ``Membership``.
        """
        return await self._repo.create_membership(membership)

    async def get_user_memberships(self, user_id) -> list[Membership]:
        """List every membership a user holds, oldest first.

        Args:
            user_id: Id of the user to list memberships for.

        Returns:
            The user's memberships, each with its organization eager-loaded.
        """
        return await self._repo.get_user_memberships(user_id)

    async def get_membership(self, user_id, organization_id) -> Membership | None:
        """Get a user's membership in one specific organization.

        Args:
            user_id: Id of the user.
            organization_id: Id of the organization.

        Returns:
            The matching ``Membership``, or ``None`` if not found.
        """
        return await self._repo.get_membership(user_id, organization_id)

    async def get_membership_by_id(self, membership_id) -> Membership | None:
        """Get a single membership by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            membership_id: Id of the membership to fetch.

        Returns:
            The matching ``Membership``, or ``None`` if not found.
        """
        return await self._repo.get_membership_by_id(membership_id)

    async def get_org_memberships(self, organization_id, page: int = 1, limit: int = 20):
        """List every membership in one organization (Team Management view).

        Args:
            organization_id: Organization to list memberships for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Membership`` rows.
        """
        return await self._repo.get_org_memberships(organization_id, page, limit)

    async def update_membership_role(self, membership: Membership, role: str) -> Membership:
        """Change a membership's role. Caller (router) commits.

        Args:
            membership: The ``Membership`` instance to update in place.
            role: New ``MembershipRole`` value to set.

        Returns:
            The updated ``Membership``.
        """
        return await self._repo.update_membership_role(membership, role)

    async def update_membership(
        self,
        target: Membership,
        caller: Membership,
        role: str | None,
        is_deactivated: bool | None,
    ) -> Membership:
        """Change a teammate's role and/or account status.

        Guardrails: can't target yourself (use change-password/account
        settings for your own account, not team management), and can't
        deactivate the org's Owner through this endpoint — there's no
        ownership-transfer flow yet, so that would permanently lock the org.

        Args:
            target: The membership being changed.
            caller: The acting membership, used for the self-targeting guard.
            role: New role to set, or ``None`` to leave it unchanged.
            is_deactivated: New activation state to set (``True``
                deactivates, ``False`` reactivates), or ``None`` to leave it
                unchanged.

        Returns:
            The updated ``Membership``.

        Raises:
            PermissionDeniedException: If the caller targets their own
                membership, or attempts to deactivate the org's Owner.
        """
        from app.core.exceptions import PermissionDeniedException

        if target.id == caller.id:
            raise PermissionDeniedException("Use your own account settings, not team management, to change yourself")

        if is_deactivated and target.is_owner:
            raise PermissionDeniedException("Cannot deactivate the organization's Owner")

        if role is not None:
            target.role = role

        if is_deactivated is not None:
            # Scoped to this membership, not the person's account globally
            # (08_DECISIONS.md 2026-09-18) — someone deactivated from this
            # org keeps full access to any other org they belong to.
            target.deactivated_at = datetime.now(UTC) if is_deactivated else None

        await self._db.flush()
        return target

    async def invite_teammate(
        self,
        organization_id,
        invited_by_user_id,
        email: str,
        role: str,
    ) -> tuple[str, Membership | Invite]:
        """Add an existing user to the org immediately, or create a pending invite.

        A pending Invite is created for an email with no account yet. If
        the email already has a deactivated membership in this org, it is
        reactivated in place rather than inserting a second row (the
        (organization_id, user_id) uniqueness constraint would otherwise be
        violated).

        Args:
            organization_id: Organization the teammate is being added to.
            invited_by_user_id: Id of the user issuing the invite, recorded
                on the ``Invite`` row when one is created.
            email: Invitee's email address.
            role: Role to grant the teammate.

        Returns:
            A tuple of ``("added", Membership)`` or ``("invited", Invite)`` —
            the caller (router) decides what to do with each, e.g.
            dispatching the invite email only for the "invited" case.

        Raises:
            AlreadyExistsException: If the invitee already has an active
                membership in the organization.
        """
        existing_user = await self._user_repo.get_user_by_email(email)

        if existing_user:
            existing_membership = await self._repo.get_membership(existing_user.id, organization_id)
            if existing_membership:
                if existing_membership.deactivated_at is None:
                    from app.core.exceptions import AlreadyExistsException
                    raise AlreadyExistsException(message="This person is already a member of your organization")

                # Previously deactivated from this org — reactivate the
                # existing row rather than trying to insert a second one
                # (organization_id, user_id) is unique, a fresh INSERT
                # would violate that constraint even though the person is
                # no longer active here.
                existing_membership.deactivated_at = None
                existing_membership.role = role
                await self._db.flush()
                await self._db.refresh(existing_membership, attribute_names=["user"])
                return "added", existing_membership

            membership = await self._repo.create_membership({
                "user_id": existing_user.id,
                "organization_id": organization_id,
                "role": role,
                "is_owner": False,
            })
            # create_membership's own refresh() only reloads column
            # attributes, not relationships — without this, serializing
            # membership.user hits a synchronous lazy-load (MissingGreenlet).
            await self._db.refresh(membership, attribute_names=["user"])
            return "added", membership

        raw_token = generate_token()
        invite = await self._invite_repo.create_invite({
            "organization_id": organization_id,
            "email": email,
            "role": role,
            "invited_by_user_id": invited_by_user_id,
            "token": hash_token(raw_token),
            "expires_at": datetime.now(UTC) + timedelta(days=settings.invite_expiry),
        })
        # Stash the raw token on the instance for the caller — it's never
        # persisted (only the hash is), so this is the one place it's
        # available after creation.
        invite.raw_token = raw_token
        return "invited", invite

    async def get_invite_by_token(self, hashed_token: str) -> Invite | None:
        """Look up a pending invite by its hashed token value.

        Args:
            hashed_token: Hash of the raw invite token from the accept link.

        Returns:
            The matching ``Invite``, or ``None`` if not found.
        """
        return await self._invite_repo.get_invite_by_token(hashed_token)

    async def mark_invite_used(self, invite_id) -> None:
        """Mark an invite as used, if it still exists.

        Args:
            invite_id: Id of the invite to mark used.
        """
        await self._invite_repo.mark_invite_used(invite_id)