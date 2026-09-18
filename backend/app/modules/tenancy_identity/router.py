import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, require_org_role
from app.core.exceptions import MembershipNotFoundException, ValidationException
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.schemas import (
    InviteTeammateRequest,
    InviteTeammateResponse,
    MembershipWithUserResponse,
    UpdateMembershipRequest,
)
from app.modules.tenancy_identity.service import MembershipService, OrganizationService
from .tasks import dispatch_invite_email

logger = logging.getLogger(__name__)

router = APIRouter()

# Founders are always registered with role=hr_administrator (auth/service.py
# register()), so gating team-management on this role also covers the Owner
# in practice today — see 08_DECISIONS.md 2026-09-13's still-open note on
# founder role. Revisit if a path is ever added for an Owner to hold a
# different role.
_TEAM_MANAGEMENT_ROLES = ("hr_administrator",)


@router.post("/memberships", status_code=200)
async def invite_teammate(
    data: InviteTeammateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_TEAM_MANAGEMENT_ROLES)),
) -> InviteTeammateResponse:
    """
    Add an existing user to the org immediately, or invite an email with no
    account yet (they accept via POST /auth/accept-invite).
    """
    service = MembershipService(db)
    status, result = await service.invite_teammate(
        organization_id=caller.organization_id,
        invited_by_user_id=caller.user_id,
        email=data.email,
        role=data.role.value,
    )
    await db.commit()

    if status == "invited":
        org_service = OrganizationService(db)
        org = await org_service.get_organization_by_id(caller.organization_id)
        invite_link = f"{settings.app_url}/accept-invite?token={quote(result.raw_token)}"
        dispatch_invite_email.delay(data.email, invite_link, org.name if org else None)
        return InviteTeammateResponse(status="invited", invite=result)

    return InviteTeammateResponse(status="added", membership=result)


@router.get("/memberships", status_code=200)
async def list_memberships(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_TEAM_MANAGEMENT_ROLES)),
) -> PaginationResponse:
    """
    List everyone in the caller's organization (Team Management screen).
    """
    service = MembershipService(db)
    result = await service.get_org_memberships(caller.organization_id, page, limit)
    result.data = [MembershipWithUserResponse.model_validate(m) for m in result.data]
    return result


@router.patch("/memberships/{membership_id}", status_code=200)
async def update_membership(
    membership_id: uuid.UUID,
    data: UpdateMembershipRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_TEAM_MANAGEMENT_ROLES)),
) -> MembershipWithUserResponse:
    """
    Change a teammate's role and/or deactivate/reactivate their account.
    """
    if not data.has_updates():
        raise ValidationException("Provide at least one of role or is_deactivated")

    service = MembershipService(db)
    # get_membership_by_id is implicitly scoped to the caller's org by RLS —
    # a membership_id from a different org comes back as None, same as a
    # genuinely nonexistent id. That's deliberate: a caller shouldn't be
    # able to tell "wrong org" apart from "doesn't exist".
    target = await service.get_membership_by_id(membership_id)
    if target is None:
        raise MembershipNotFoundException()

    updated = await service.update_membership(
        target=target,
        caller=caller,
        role=data.role.value if data.role else None,
        is_deactivated=data.is_deactivated,
    )
    await db.commit()
    await db.refresh(updated, attribute_names=["user"])

    return MembershipWithUserResponse.model_validate(updated)
