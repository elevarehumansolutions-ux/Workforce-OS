"""FastAPI routes for the KPI module.

Single-KPI CRUD (``POST|GET|PATCH /kpis``) and the group-level reconcile
(``PUT /departments/{id}/kpis``) are ``hr_administrator``-only for
mutations; reads are open to any authenticated org member — same
precedent as OKRs/Business DNA/Org Structure (08_DECISIONS.md 2026-09-30).
The scores upsert is the one exception: ``hr_administrator`` **or**
``business_executive``, repeatable while the quarter is still open
(08_DECISIONS.md 2026-09-29).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db, require_org_role
from app.core.exceptions import KPINotFoundException
from app.core.schemas import PaginationResponse
from app.core.triggers import trigger_ai_suggestion_generation
from app.modules.tenancy_identity.models import Membership

from .schemas import (
    KPICreate,
    KPIGroupUpdateRequest,
    KPIGroupUpdateResponse,
    KPIResponse,
    KPIScoreCreate,
    KPIScoreResponse,
    KPIUpdate,
)
from .service import KPIService

router = APIRouter()

_WRITE_ROLES = ("hr_administrator",)
_SCORE_WRITE_ROLES = ("hr_administrator", "business_executive")


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

@router.post("/kpis", status_code=200)
async def create_kpi(
    data: KPICreate,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> KPIResponse:
    """Create a KPI in the caller's organization.

    Requires the HR Administrator role. 409 (``KPI_WEIGHT_MISMATCH``) if
    adding it would push its department/location group's weights over
    100%.

    Args:
        data: KPI fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created KPI.
    """
    service = KPIService(db)
    kpi = await service.create_kpi(caller.organization_id, caller.user_id, data)
    await db.commit()
    # A KPI created is the obvious kpi_weight generation event, matching
    # the "specific event, not every write" pattern already used for
    # departments/positions/OKRs — fires unconditionally, same as a new
    # position, since there's no equivalent of departments' is_critical
    # gate here.
    await trigger_ai_suggestion_generation(caller.organization_id)
    return KPIResponse.model_validate(kpi)


@router.get("/kpis", status_code=200)
async def list_kpis(
    department_id: uuid.UUID | None = Query(default=None),
    location_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted KPIs for the caller's organization.

    Open to any authenticated member of the organization — an Employee in
    one department can read another department's KPIs, same as OKRs and
    Business DNA (08_DECISIONS.md 2026-09-30).

    Args:
        department_id: If given, restrict results to this department.
        location_id: If given, restrict results to this location.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of KPIs.
    """
    service = KPIService(db)
    result = await service.kpi_repo.list_kpis(
        caller.organization_id, department_id, location_id, page, limit
    )
    result.data = [KPIResponse.model_validate(kpi) for kpi in result.data]
    return result


@router.get("/kpis/{kpi_id}", status_code=200)
async def get_kpi(
    kpi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> KPIResponse:
    """Get a single KPI by id.

    Open to any authenticated member of the organization.

    Args:
        kpi_id: Id of the KPI to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        The matching KPI.

    Raises:
        KPINotFoundException: If no non-deleted KPI with that id exists
            in the caller's org (translates to a 404 response).
    """
    kpi = await KPIService(db).kpi_repo.get_kpi_by_id(kpi_id)
    if kpi is None:
        raise KPINotFoundException()
    return KPIResponse.model_validate(kpi)


@router.patch("/kpis/{kpi_id}", status_code=200)
async def update_kpi(
    kpi_id: uuid.UUID,
    data: KPIUpdate,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> KPIResponse:
    """Apply a partial update to a KPI.

    Requires the HR Administrator role. Only re-validates the weight
    group when ``weight`` is one of the fields being changed.

    Args:
        kpi_id: Id of the KPI to update.
        data: Fields to update.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated KPI.

    Raises:
        KPINotFoundException: If no non-deleted KPI with that id exists
            in the caller's org (translates to a 404 response).
    """
    kpi = await KPIService(db).update_kpi(kpi_id, caller.user_id, data)
    await db.commit()
    return KPIResponse.model_validate(kpi)


# ---------------------------------------------------------------------------
# Group reconcile — the only way to delete a KPI
# ---------------------------------------------------------------------------

@router.put("/departments/{department_id}/kpis", status_code=200)
async def reconcile_kpis(
    department_id: uuid.UUID,
    data: KPIGroupUpdateRequest,
    location_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> KPIGroupUpdateResponse:
    """Reconcile a department/location's whole KPI list in one call.

    Requires the HR Administrator role. An item with an ``id`` is
    updated, an item with no ``id`` is created, and an existing KPI whose
    id is missing from the submitted list is deleted — this is the only
    way to delete a KPI, there is no standalone ``DELETE /kpis/{id}``.
    The submitted list's weights must sum to exactly 100 (409
    ``KPI_WEIGHT_MISMATCH`` otherwise, with the actual total in the
    message).

    Args:
        department_id: The group's department.
        data: The department/location group's whole desired KPI list.
        location_id: The group's location, or omitted for the
            department-wide group.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The full resulting KPI list, with real ids for anything newly
        created.
    """
    service = KPIService(db)
    kpis = await service.reconcile_kpis(
        caller.organization_id, caller.user_id, department_id, location_id, data
    )
    await db.commit()
    await trigger_ai_suggestion_generation(caller.organization_id)
    return KPIGroupUpdateResponse(
        kpis=[KPIResponse.model_validate(kpi) for kpi in kpis]
    )


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

@router.post("/kpis/{kpi_id}/scores", status_code=200)
async def upsert_score(
    kpi_id: uuid.UUID,
    data: KPIScoreCreate,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_SCORE_WRITE_ROLES)),
) -> KPIScoreResponse:
    """Upsert the current, still-open period's actual value for a KPI.

    Requires the HR Administrator or Business Executive role.
    Repeatable while the period is still open, so progress is visible
    mid-quarter, not just at close (08_DECISIONS.md 2026-09-29). 409
    (``KPI_SCORE_PERIOD_CLOSED``) once ``period_end`` has passed — a
    correction after that point is a new period's row, not an edit to
    this one.

    Args:
        kpi_id: Id of the KPI this score is for.
        data: The period and its actual value.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or
            Business Executive.

    Returns:
        The created or updated score, with ``score_percentage`` computed
        server-side.

    Raises:
        KPINotFoundException: If no non-deleted KPI with that id exists
            in the caller's org (translates to a 404 response).
    """
    score = await KPIService(db).upsert_score(caller.organization_id, caller.user_id, kpi_id, data)
    await db.commit()
    return KPIScoreResponse.model_validate(score)


@router.get("/kpis/{kpi_id}/scores", status_code=200)
async def list_scores(
    kpi_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List a KPI's historical scores, newest period first.

    Open to any authenticated member of the organization.

    Args:
        kpi_id: KPI whose scores to list.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of scores.
    """
    result = await KPIService(db).score_repo.list_scores_for_kpi(kpi_id, page, limit)
    result.data = [KPIScoreResponse.model_validate(score) for score in result.data]
    return result
