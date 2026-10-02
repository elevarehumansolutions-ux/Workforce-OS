"""FastAPI routes for the attendance module.

Clock in, clock out, and read attendance history. Attendance belongs to the
employee record, not the role: any authenticated member who also has an
employee record can clock in and out. History is the caller's own by default;
HR administrators and business executives may read anyone's.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.models import Membership

from .schemas import AttendanceRecordResponse, ClockInResponse
from .service import AttendanceService

router = APIRouter()


@router.post("/attendance/clock-in", status_code=200)
async def clock_in(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> ClockInResponse:
    """Clock the caller in, or return the record they are already clocked in on.

    Clocking in twice is a harmless retry, not an error: the response says
    ``already_clocked_in: true`` and returns the existing open record.
    Open to any authenticated member who has an employee record.

    Args:
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The open record and whether it already existed.

    Raises:
        NoEmployeeProfileException: If the caller has no employee record
            (translates to a 409 response).
        ValidationException: If the caller's employee has been offboarded
            (translates to a 422 response).
    """
    record, already = await AttendanceService(db).clock_in(caller.user_id, caller.organization_id)
    await db.commit()
    return ClockInResponse(
        already_clocked_in=already, record=AttendanceRecordResponse.model_validate(record)
    )


@router.post("/attendance/clock-out", status_code=200)
async def clock_out(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> AttendanceRecordResponse:
    """Clock the caller out of their open record.

    Open to any authenticated member who has an employee record.

    Args:
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The closed record.

    Raises:
        NoEmployeeProfileException: If the caller has no employee record
            (translates to a 409 response).
        NotClockedInException: If the caller has no open record (translates
            to a 409 response).
    """
    record = await AttendanceService(db).clock_out(caller.user_id, caller.organization_id)
    await db.commit()
    return AttendanceRecordResponse.model_validate(record)


@router.get("/attendance", status_code=200)
async def list_attendance(
    employee_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List attendance history, newest clock-in first.

    With no ``employee_id`` this is the caller's own history. HR
    administrators and business executives may pass any employee of the
    organization. ``date_from`` and ``date_to`` are calendar days (inclusive)
    on the organization's wall clock, i.e. in its configured timezone. The
    most recent record with a null ``clock_out_at`` means the employee is
    clocked in right now.

    Args:
        employee_id: Whose history to read; omit for the caller's own.
        date_from: First day to include.
        date_to: Last day to include.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        A paginated response of attendance records.

    Raises:
        ValidationException: If ``date_from`` is after ``date_to`` (422).
        NoEmployeeProfileException: If asking for their own history without
            an employee record (409).
        PermissionDeniedException: If a role without access asks for
            someone else's history (403).
        EmployeeNotFoundException: If ``employee_id`` is not an employee of
            this organization (404).
    """
    result = await AttendanceService(db).list_history(
        caller, employee_id, date_from, date_to, page, limit
    )
    result.data = [AttendanceRecordResponse.model_validate(r) for r in result.data]
    return result
