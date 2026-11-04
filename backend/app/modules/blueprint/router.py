"""FastAPI routes for the blueprint: the AI-proposed departments, positions and OKRs.

Reading and reviewing is for HR Administrator and Business Executive, the
same two roles that review AI suggestions. Asking for a new blueprint is HR
only. The router owns the transaction: the service never commits, so a failed
apply rolls the whole request back.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_org_role
from app.core.schemas import PaginationResponse
from app.core.triggers import trigger_ai_suggestion_generation, trigger_blueprint_generation
from app.modules.tenancy_identity.models import Membership

from .enums import BlueprintKind, BlueprintStatus
from .repository import BlueprintRepository
from .schemas import (
    AcceptAllResponse,
    BlueprintEditRequest,
    BlueprintItemResponse,
    GenerateResponse,
)
from .service import BlueprintService

router = APIRouter()

_REVIEW_ROLES = ("hr_administrator", "business_executive")
_GENERATE_ROLES = ("hr_administrator",)


@router.get("/blueprint", status_code=200)
async def list_blueprint_items(
    status: BlueprintStatus | None = Query(default=None),
    kind: BlueprintKind | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> PaginationResponse:
    """List the organization's blueprint items, newest batch first, in the AI's own order.

    Args:
        status: Only items in this review state (the review screen asks for ``pending``).
        kind: Only this kind of item.
        page: 1-indexed page number.
        limit: Rows per page (1-100; a whole blueprint normally fits in one page).
        db: Database session dependency.
        caller: HR Administrator or Business Executive.
    """
    result = await BlueprintService(db).list_items(
        caller.organization_id,
        status.value if status else None,
        kind.value if kind else None,
        page,
        limit,
    )
    result.data = [BlueprintItemResponse.model_validate(row) for row in result.data]
    return result


@router.post("/blueprint/generate", status_code=202)
async def generate_blueprint(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_GENERATE_ROLES)),
) -> GenerateResponse:
    """Ask the AI for a (new) blueprint. Runs in the background; poll ``GET /blueprint``.

    If a blueprint is still waiting for review nothing is queued: review or reject it first.
    """
    if await BlueprintRepository(db).has_pending_items(caller.organization_id):
        return GenerateResponse(status="already_pending")
    await trigger_blueprint_generation(caller.organization_id, first_time_only=False)
    return GenerateResponse(status="queued")


@router.post("/blueprint/accept-all", status_code=200)
async def accept_all(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> AcceptAllResponse:
    """Approve every pending item at once, parents first.

    Items that cannot be applied (say a rename that clashes with an existing
    name) are left pending and listed in ``skipped`` with the reason.
    """
    result = await BlueprintService(db).accept_all(caller.organization_id, caller.user_id)
    await db.commit()
    if result.accepted:
        # The structure changed, so the critical-role and revenue suggestions can now be worked out.
        await trigger_ai_suggestion_generation(caller.organization_id)
    return result


@router.post("/blueprint/{item_id}/approve", status_code=200)
async def approve_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Approve one item as proposed. Its pending parents are approved first."""
    item = await BlueprintService(db).approve_item(item_id, caller.user_id)
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    await trigger_ai_suggestion_generation(caller.organization_id)
    return response


@router.post("/blueprint/{item_id}/edit", status_code=200)
async def edit_item(
    item_id: uuid.UUID,
    data: BlueprintEditRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Approve one item with corrected wording."""
    item = await BlueprintService(db).edit_item(item_id, caller.user_id, data.title)
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    await trigger_ai_suggestion_generation(caller.organization_id)
    return response


@router.post("/blueprint/{item_id}/reject", status_code=200)
async def reject_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Reject one item. Items that depend on it cannot be approved afterwards."""
    item = await BlueprintService(db).reject_item(item_id, caller.user_id)
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    return response
