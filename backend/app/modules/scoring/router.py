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
from .schemas import (
    CompanyPerformanceResponse,
    DepartmentPerformanceResponse,
    LeaderboardResponse,
    MostImprovedResponse,
    PersonPerformanceResponse,
)

router = APIRouter()


@router.get("/company-performance-summary", status_code=200)
async def get_company_performance(
    period_start: date | None = Query(None, description="First day of the period; with period_end, or neither"),
    period_end: date | None = Query(None, description="Last day of the period"),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> CompanyPerformanceResponse:
    """The company dashboard: headline score, company punctuality, the departments behind them and a 4-quarter trend.

    The headline is the departments' KPI results weighted by revenue share
    ("N of M departments counted"); punctuality pools every department's tasks.
    The two are never blended. Only HR administrators and business executives
    may open it.

    Args:
        period_start: First day of the period, or leave both dates out.
        period_end: Last day of the period.
        db: Database session dependency.
        caller: The authenticated caller's membership.

    Raises:
        OrganizationNotFoundException: The caller may not see the company view (404).
        ValidationException: Only one date given, or the end is before the start (422).
    """
    service = PerformanceReadService(db)
    return await service.get_company_performance(caller, period_start, period_end)


@router.get("/company-performance-summary/most-improved", status_code=200)
async def get_most_improved(
    period_start: date | None = Query(None, description="First day of the period; with period_end, or neither"),
    period_end: date | None = Query(None, description="Last day of the period"),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> MostImprovedResponse:
    """The top three people and the top three departments by gain in points since the quarter before.

    A recognition list with the context of each entry (both scores and both task
    counts). Needs at least 10 valid tasks in both quarters; fewer than three
    entries (or none) is normal. Only HR administrators and business executives.

    Raises:
        OrganizationNotFoundException: The caller may not see the company view (404).
        ValidationException: Only one date given, or the end is before the start (422).
    """
    service = PerformanceReadService(db)
    return await service.get_most_improved(caller, period_start, period_end)


@router.get("/departments/{department_id}/performance-summary", status_code=200)
async def get_department_performance(
    department_id: uuid.UUID,
    period_start: date | None = Query(None, description="First day of the period; with period_end, or neither"),
    period_end: date | None = Query(None, description="Last day of the period"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> DepartmentPerformanceResponse:
    """A department's two numbers for a period, with one page of its people.

    "Hit its goals" (KPI results) and "team punctuality" are shown side by side
    and never blended. HR and executives may open any department; a head or
    manager only their own (see ``PerformanceScope``).

    Args:
        department_id: The department.
        period_start: First day of the period, or leave both dates out.
        period_end: Last day of the period.
        page: Page of the people list (1-based).
        limit: People per page (1 to 100).
        db: Database session dependency.
        caller: The authenticated caller's membership.

    Raises:
        DepartmentNotFoundException: No such department, or the caller may not see it (404).
        ValidationException: Only one date given, or the end is before the start (422).
    """
    service = PerformanceReadService(db)
    return await service.get_department_performance(caller, department_id, period_start, period_end, page, limit)


@router.get("/employees/leaderboard", status_code=200)
async def get_leaderboard(
    department_id: uuid.UUID | None = Query(None, description="Only this department"),
    period_start: date | None = Query(None, description="First day of the period; with period_end, or neither"),
    period_end: date | None = Query(None, description="Last day of the period"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> LeaderboardResponse:
    """People ranked by overall score, with their task counts beside the score.

    HR and executives rank everyone (or one department); a department head or
    manager only their own departments; an ordinary employee gets 404. Equal
    scores share a rank; people with no data are not listed.

    Must be mounted before the organization router in ``main.py``, which has
    ``/employees/{employee_id}`` and would otherwise read "leaderboard" as an id.

    Raises:
        EmployeeNotFoundException: The caller may not see a ranked list (404).
        DepartmentNotFoundException: Unknown or unseen ``department_id`` (404).
        ValidationException: Only one date given, or the end is before the start (422).
    """
    service = PerformanceReadService(db)
    return await service.get_leaderboard(caller, department_id, period_start, period_end, page, limit)


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
