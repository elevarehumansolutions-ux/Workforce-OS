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
    HistoryEntryResponse,
    HistoryResponse,
    UndoPreviewResponse,
    UndoResponse,
)
from .history import BlueprintHistory, details_to_plain
from .reshape import BlueprintReshaper
from .service import BlueprintService
from .undo import BlueprintUndo

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
    history = BlueprintHistory(db)
    mark = await history.begin(caller.organization_id)
    result = await BlueprintService(db).accept_all(caller.organization_id, caller.user_id)
    await history.record(
        mark, caller.user_id, "accept_all", f"Added everything waiting ({result.accepted} items)", {}
    )
    await db.commit()
    # No AI Suggestions run here on purpose: the blueprint already decided the critical
    # departments and roles, the capital shares and the KPI weights, so asking the old
    # engine again would duplicate them. It still runs on later changes (new objective, ...).
    return result


@router.get("/blueprint/history", status_code=200)
async def get_history(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> HistoryResponse:
    """The last changes made while reviewing the plan, newest first, each saying if it can be undone or redone."""
    entries = await BlueprintHistory(db).list_entries(caller.organization_id)
    return HistoryResponse(data=[HistoryEntryResponse(**entry) for entry in entries])


@router.post("/blueprint/history/{action_id}/undo", status_code=200)
async def undo_change(
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> HistoryResponse:
    """Take one change back. 409 ``BLUEPRINT_HISTORY_BLOCKED`` (with the reason) when something later depends on it."""
    history = BlueprintHistory(db)
    await history.undo(action_id, caller.user_id)
    entries = await history.list_entries(caller.organization_id)
    await db.commit()
    return HistoryResponse(data=[HistoryEntryResponse(**entry) for entry in entries])


@router.post("/blueprint/history/{action_id}/redo", status_code=200)
async def redo_change(
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> HistoryResponse:
    """Do an undone change again. Only the most recently undone one, so changes come back in order."""
    history = BlueprintHistory(db)
    await history.redo(action_id, caller.user_id)
    entries = await history.list_entries(caller.organization_id)
    await db.commit()
    return HistoryResponse(data=[HistoryEntryResponse(**entry) for entry in entries])


@router.post("/blueprint/{item_id}/approve", status_code=200)
async def approve_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Approve one item as proposed. Its pending parents are approved first."""
    history = BlueprintHistory(db)
    mark = await history.begin(caller.organization_id)
    item = await BlueprintService(db).approve_item(item_id, caller.user_id)
    await history.record(
        mark, caller.user_id, "approve", history.label_for_add(mark, item_id), {"item_id": str(item_id)}
    )
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
    history = BlueprintHistory(db)
    mark = await history.begin(caller.organization_id)
    item = await BlueprintService(db).edit_item(item_id, caller.user_id, data.title, details)
    await history.record(
        mark,
        caller.user_id,
        "edit",
        history.label_for_add(mark, item_id, data.title.strip()),
        {"item_id": str(item_id), "title": data.title.strip(), "details": details_to_plain(details)},
    )
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
    history = BlueprintHistory(db)
    mark = await history.begin(caller.organization_id)
    item = await BlueprintService(db).reject_item(item_id, caller.user_id)
    await history.record(
        mark, caller.user_id, "reject", history.label_for_skip(mark, item_id), {"item_id": str(item_id)}
    )
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    return response


@router.get("/blueprint/{item_id}/undo-preview", status_code=200)
async def undo_preview(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> UndoPreviewResponse:
    """What undoing an added item would also remove (counts by kind). Changes nothing."""
    item, counts = await BlueprintUndo(db).preview(item_id)
    return UndoPreviewResponse(
        title=item.reviewed_title or item.title,
        kind=item.kind,
        removes=counts,
        total=sum(counts.values()),
    )


@router.post("/blueprint/{item_id}/undo", status_code=200)
async def undo_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> UndoResponse:
    """Undo an added item: remove its real row and everything added under it, back to waiting.

    If another module refuses a removal (a person still holds the role, a task still points at
    it) the answer is that refusal (409 ``RESOURCE_IN_USE``) and nothing is changed.
    """
    undone = await BlueprintUndo(db).undo(item_id, caller.user_id)
    await db.commit()
    return UndoResponse(undone=undone)


@router.post("/blueprint/{item_id}/add-separately", status_code=200)
async def add_separately(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Turn a left-out item back into its own pending department or role."""
    history = BlueprintHistory(db)
    mark = await history.begin(caller.organization_id)
    item = await BlueprintReshaper(db).add_separately(item_id)
    await history.record(
        mark, caller.user_id, "add_separately", history.label_for_add_back(mark, item), {"item_id": str(item_id)}
    )
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    return response


@router.post("/blueprint/{item_id}/undo-merge", status_code=200)
async def undo_merge(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> BlueprintItemResponse:
    """Reverse a merge: a left-out note becomes its own department or role again, with its things back.

    Only while everything the merge touched is still waiting; 422 once any of it was added.
    """
    item = await BlueprintReshaper(db).undo_merge(item_id, caller.user_id)
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
    history = BlueprintHistory(db)
    mark = await history.begin(caller.organization_id)
    if data.target_id is not None:
        item = await BlueprintReshaper(db).merge(item_id, data.target_id)
    else:
        item = await BlueprintReshaper(db).merge_into_existing(item_id, data.existing_id, caller.user_id)
    await history.record(
        mark,
        caller.user_id,
        "merge",
        await history.label_for_merge(mark, item_id, data.target_id, data.existing_id),
        {
            "item_id": str(item_id),
            "target_id": str(data.target_id) if data.target_id else None,
            "existing_id": str(data.existing_id) if data.existing_id else None,
        },
    )
    response = BlueprintItemResponse.model_validate(item)
    await db.commit()
    return response
