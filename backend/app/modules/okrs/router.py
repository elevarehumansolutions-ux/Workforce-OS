"""FastAPI routes for the OKR module.

Exposes OKR and key-result CRUD. Reads are open to any authenticated org
member; mutations are gated to HR Administrator (08_DECISIONS.md
2026-09-21 — Business Executive and Manager both deliberately excluded,
matching the Org Structure/Business DNA precedent). No DELETE endpoints —
deferred to M8 alongside the ``kpis.key_result_id`` reference guard.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db, require_org_role
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.models import Membership

from .schemas import (
    KeyResultCreateRequest,
    KeyResultResponse,
    KeyResultUpdateRequest,
    OKRCreateRequest,
    OKRResponse,
    OKRUpdateRequest,
)
from .service import KeyResultService, OKRService

router = APIRouter()

_WRITE_ROLES = ("hr_administrator",)


# ---------------------------------------------------------------------------
# OKRs
# ---------------------------------------------------------------------------

@router.post("/okrs", status_code=200)
async def create_okr(
    data: OKRCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> OKRResponse:
    """Create an OKR in the caller's organization.

    Requires the HR Administrator role.

    Args:
        data: OKR fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created OKR.
    """
    service = OKRService(db)
    okr = await service.create_okr(caller.organization_id, caller.user_id, data.model_dump())
    await db.commit()
    return OKRResponse.model_validate(okr)


@router.get("/okrs", status_code=200)
async def list_okrs(
    department_id: uuid.UUID | None = Query(default=None),
    location_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted OKRs for the caller's organization.

    Open to any authenticated member of the organization.

    Args:
        department_id: If given, restrict results to this department.
        location_id: If given, restrict results to this location.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of OKRs.
    """
    service = OKRService(db)
    result = await service.list_okrs(
        caller.organization_id, department_id, location_id, page, limit
    )
    result.data = [OKRResponse.model_validate(okr) for okr in result.data]
    return result


@router.get("/okrs/{okr_id}", status_code=200)
async def get_okr(
    okr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> OKRResponse:
    """Get a single OKR by id.

    Open to any authenticated member of the organization.

    Args:
        okr_id: Id of the OKR to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        The matching OKR.

    Raises:
        OKRNotFoundException: If no non-deleted OKR with that id exists in
            the caller's org (translates to a 404 response).
    """
    service = OKRService(db)
    okr = await service.get_okr_by_id(okr_id)
    return OKRResponse.model_validate(okr)


@router.patch("/okrs/{okr_id}", status_code=200)
async def update_okr(
    okr_id: uuid.UUID,
    data: OKRUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> OKRResponse:
    """Apply a partial update to an OKR.

    Requires the HR Administrator role.

    Args:
        okr_id: Id of the OKR to update.
        data: Fields to update.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated OKR.

    Raises:
        OKRNotFoundException: If no non-deleted OKR with that id exists in
            the caller's org (translates to a 404 response).
    """
    service = OKRService(db)
    okr = await service.update_okr(okr_id, caller.user_id, data.model_dump(exclude_unset=True))
    await db.commit()
    return OKRResponse.model_validate(okr)


# ---------------------------------------------------------------------------
# Key results
# ---------------------------------------------------------------------------

@router.post("/okrs/{okr_id}/key-results", status_code=200)
async def create_key_result(
    okr_id: uuid.UUID,
    data: KeyResultCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> KeyResultResponse:
    """Add a key result to an OKR.

    Requires the HR Administrator role.

    Args:
        okr_id: Id of the OKR to add the key result to.
        data: Key result fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created key result.

    Raises:
        OKRNotFoundException: If no non-deleted OKR with that id exists in
            the caller's org (translates to a 404 response).
    """
    service = KeyResultService(db)
    key_result = await service.create_key_result(okr_id, caller.user_id, data.model_dump())
    await db.commit()
    return KeyResultResponse.model_validate(key_result)


@router.get("/okrs/{okr_id}/key-results", status_code=200)
async def list_key_results(
    okr_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted key results for an OKR.

    Open to any authenticated member of the organization.

    Args:
        okr_id: Id of the OKR to list key results for.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of key results.

    Raises:
        OKRNotFoundException: If no non-deleted OKR with that id exists in
            the caller's org (translates to a 404 response).
    """
    service = KeyResultService(db)
    result = await service.list_key_results(okr_id, page, limit)
    result.data = [KeyResultResponse.model_validate(kr) for kr in result.data]
    return result


@router.patch("/key-results/{key_result_id}", status_code=200)
async def update_key_result(
    key_result_id: uuid.UUID,
    data: KeyResultUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> KeyResultResponse:
    """Apply a partial update to a key result.

    Requires the HR Administrator role.

    Args:
        key_result_id: Id of the key result to update.
        data: Fields to update.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated key result.

    Raises:
        KeyResultNotFoundException: If no non-deleted key result with that
            id exists in the caller's org (translates to a 404 response).
    """
    service = KeyResultService(db)
    key_result = await service.update_key_result(
        key_result_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()
    return KeyResultResponse.model_validate(key_result)
