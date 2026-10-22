"""FastAPI routes for the Scoring module (the reads).

Every route here only reads saved scores. What each caller may see is decided
in ``PerformanceScope`` (``access.py``); anything unseen is a 404.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db
from app.modules.tenancy_identity.models import Membership

from .reads import PerformanceReadService
from .schemas import PersonPerformanceResponse

router = APIRouter()


@router.get("/employees/me/performance", status_code=200)
async def get_my_performance(
    period_start: date | None = Query(None, description="First day of the period; with period_end, or neither"),
    period_end: date | None = Query(None, description="Last day of the period"),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PersonPerformanceResponse:
    """The caller's own performance card for a period (the current quarter if no dates are given).

    Registered before the by-id route below so that "me" is never read as an id.

    Args:
        period_start: First day of the period, or leave both dates out.
        period_end: Last day of the period.
        db: Database session dependency.
        caller: The authenticated caller's membership.

    Returns:
        Per-KPI results, the overall score and "N of M counted". A score with
        no data is ``null`` with a reason, never 0.

    Raises:
        EmployeeNotFoundException: The caller has no employee record (404).
        ValidationException: Only one date given, or the end is before the start (422).
    """
    service = PerformanceReadService(db)
    return await service.get_person_performance(caller, None, period_start, period_end)


@router.get("/employees/{employee_id}/performance", status_code=200)
async def get_person_performance(
    employee_id: uuid.UUID,
    period_start: date | None = Query(None, description="First day of the period; with period_end, or neither"),
    period_end: date | None = Query(None, description="Last day of the period"),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PersonPerformanceResponse:
    """A person's performance card for a period, for the people the caller may see.

    HR and executives see everyone; a department head or manager sees their
    department's people; an employee sees only themselves (see ``PerformanceScope``).

    Args:
        employee_id: The person.
        period_start: First day of the period, or leave both dates out.
        period_end: Last day of the period.
        db: Database session dependency.
        caller: The authenticated caller's membership.

    Raises:
        EmployeeNotFoundException: No such person, or the caller may not see them (404).
        ValidationException: Only one date given, or the end is before the start (422).
    """
    service = PerformanceReadService(db)
    return await service.get_person_performance(caller, employee_id, period_start, period_end)
