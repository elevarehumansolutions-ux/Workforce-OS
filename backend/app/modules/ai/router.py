"""FastAPI routes for AI suggestions.

Listing and review actions (approve, edit, reject) are open to HR
Administrator and Business Executive only — suggestions carry revenue
allocations and critical-role judgments derived from the capital investment
figure, which is already restricted to those two roles (08_DECISIONS.md
2026-09-21; review widened to both roles 2026-09-24). The router owns the transaction: the service never commits, so
a service error (404/409/422, or a failed apply) rolls the whole request back.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_org_role
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.models import Membership

from .enums import SuggestionStatus, SuggestionType
from .schemas import AISuggestionEditRequest, AISuggestionResponse
from .service import AISuggestionService

router = APIRouter()

_REVIEW_ROLES = ("hr_administrator", "business_executive")
_READ_ROLES = ("hr_administrator", "business_executive")


@router.get("/ai-suggestions", status_code=200)
async def list_suggestions(
    status: SuggestionStatus | None = Query(default=None),
    suggestion_type: SuggestionType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_READ_ROLES)),
) -> PaginationResponse:
    """List the caller's organization's AI suggestions, newest first.

    Requires the HR Administrator or Business Executive role.

    Args:
        status: If given, restrict results to this review status.
        suggestion_type: If given, restrict results to this suggestion type.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of suggestions.
    """
    result = await AISuggestionService(db).list_suggestions(
        caller.organization_id,
        status.value if status else None,
        suggestion_type.value if suggestion_type else None,
        page,
        limit,
    )
    result.data = [AISuggestionResponse.model_validate(row) for row in result.data]
    return result


@router.post("/ai-suggestions/{suggestion_id}/approve", status_code=200)
async def approve_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> AISuggestionResponse:
    """Approve a pending suggestion exactly as the AI proposed, and apply it.

    Requires the HR Administrator or Business Executive role. No body — to
    change a value, use ``/edit``. If applying it fails (e.g. a department
    with that name now exists), the request rolls back and the suggestion
    stays pending.

    Args:
        suggestion_id: Id of the suggestion to approve.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or
            Business Executive.

    Returns:
        The approved suggestion.
    """
    suggestion = await AISuggestionService(db).approve_suggestion(suggestion_id, caller.user_id)
    await db.commit()
    return suggestion


@router.post("/ai-suggestions/{suggestion_id}/edit", status_code=200)
async def edit_suggestion(
    suggestion_id: uuid.UUID,
    edit: AISuggestionEditRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> AISuggestionResponse:
    """Correct a pending suggestion's values, then apply the corrected version.

    Requires the HR Administrator or Business Executive role. Send only the
    fields being changed; anything left out keeps the AI's value. 422 if a
    field doesn't apply to the suggestion's type, the body is empty, or
    nothing differs from the AI's proposal (call ``/approve`` instead).

    Args:
        suggestion_id: Id of the suggestion to edit.
        edit: The fields being changed.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or
            Business Executive.

    Returns:
        The edited suggestion.
    """
    suggestion = await AISuggestionService(db).edit_suggestion(suggestion_id, caller.user_id, edit)
    await db.commit()
    return suggestion


@router.post("/ai-suggestions/{suggestion_id}/reject", status_code=200)
async def reject_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_REVIEW_ROLES)),
) -> AISuggestionResponse:
    """Reject a pending suggestion.

    Requires the HR Administrator or Business Executive role. Starts the
    quarterly suppression, so the same suggestion isn't proposed again this
    fiscal quarter.

    Args:
        suggestion_id: Id of the suggestion to reject.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or
            Business Executive.

    Returns:
        The rejected suggestion.
    """
    suggestion = await AISuggestionService(db).reject_suggestion(suggestion_id, caller.user_id)
    await db.commit()
    return suggestion
