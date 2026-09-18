from datetime import UTC, datetime, timedelta

from .repository import UserRepository, OrganizationRepository, MembershipRepository, InviteRepository
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, Organization, Membership, Invite
from app.core.security import generate_token, hash_token
from app.core.config import settings


class UserService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = UserRepository(db)
    
    async def get_user_by_email(self, email: str) -> User:
        return await self._repo.get_user_by_email(email)

    async def get_user_by_id(self, user_id) -> User | None:
        return await self._repo.get_user_by_id(user_id)
    
    async def create_user(self, user: dict) -> User:
        return await self._repo.create_user(user)

    async def update_account_status(self, user_id, status: str) -> User:
        return await self._repo.update_account_status(user_id, status)


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = OrganizationRepository(db)

    async def create_organization(self, organization: dict | None = None) -> Organization:
        return await self._repo.create_organization(organization)

    async def get_organization_by_id(self, organization_id) -> Organization | None:
        return await self._repo.get_organization_by_id(organization_id)


class MembershipService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = MembershipRepository(db)
        self._user_repo = UserRepository(db)
        self._invite_repo = InviteRepository(db)

    async def create_membership(self, membership: dict) -> Membership:
        return await self._repo.create_membership(membership)

    async def get_user_memberships(self, user_id) -> list[Membership]:
        return await self._repo.get_user_memberships(user_id)

    async def get_membership(self, user_id, organization_id) -> Membership | None:
        return await self._repo.get_membership(user_id, organization_id)

    async def get_membership_by_id(self, membership_id) -> Membership | None:
        return await self._repo.get_membership_by_id(membership_id)

    async def get_org_memberships(self, organization_id) -> list[Membership]:
        return await self._repo.get_org_memberships(organization_id)

    async def update_membership_role(self, membership: Membership, role: str) -> Membership:
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
        """Add an existing user to the org immediately, or create a pending
        Invite for an email with no account yet.

        Returns ("added", Membership) or ("invited", Invite) — the caller
        (router) decides what to do with each, e.g. dispatching the invite
        email only for the "invited" case.
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
        return await self._invite_repo.get_invite_by_token(hashed_token)

    async def mark_invite_used(self, invite_id) -> None:
        await self._invite_repo.mark_invite_used(invite_id)