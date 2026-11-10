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
from app.core.exceptions import ValidationException
from app.core.schemas import PaginationResponse
from app.core.triggers import trigger_blueprint_generation
from app.modules.tenancy_identity.models import Membership

from .enums import BlueprintKind, BlueprintStatus
from .repository import BlueprintRepository
from .schemas import (
    AcceptAllResponse,
    BlueprintEditRequest,
    BlueprintItemResponse,
    BlueprintMergeRequest,
    GenerateResponse,
)
from .reshape import BlueprintReshaper
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
    # No AI Suggestions run here on purpose: the blueprint already decided the critical
    # departments and roles, the capital shares and the KPI weights, so asking the old
    # engine again would duplicate them. It still runs on later changes (new objective, ...).
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
    return response


@router.post("/blueprint/{item_id}/edit", status_code=200)
async def edit_item(
    item_id: uuid.UUID,
    data: BlueprintEditRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Approve one item with corrected wording and, for a KPI or a department, corrected details."""
    details = data.model_dump(exclude_unset=True, exclude={"title"})
    item = await BlueprintService(db).edit_item(item_id, caller.user_id, data.title, details)
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
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


@router.post("/blueprint/{item_id}/add-separately", status_code=200)
async def add_separately(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Turn a left-out item back into its own pending department or role."""
    item = await BlueprintReshaper(db).add_separately(item_id)
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    return response


@router.post("/blueprint/{item_id}/merge", status_code=200)
async def merge_item(
    item_id: uuid.UUID,
    data: BlueprintMergeRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Merge a suggested department or role into another one; the first becomes a left-out note."""
    if (data.target_id is None) == (data.existing_id is None):
        raise ValidationException(message="Give either target_id or existing_id, not both and not neither.")
    if data.target_id is not None:
        item = await BlueprintReshaper(db).merge(item_id, data.target_id)
    else:
        item = await BlueprintReshaper(db).merge_into_existing(item_id, data.existing_id, caller.user_id)
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    return response
