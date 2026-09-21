"""FastAPI routes for the organization structure module.

Exposes CRUD endpoints for locations, departments, positions, and employees,
plus dedicated offboard/reinstate actions for employees. Reads are open to
any authenticated org member; mutations are gated to HR Administrator.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_membership, require_org_role
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.models import Membership

from .schemas import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
    EmployeeCreateRequest,
    EmployeeResponse,
    EmployeeUpdateRequest,
    LocationCreateRequest,
    LocationResponse,
    LocationUpdateRequest,
    PositionCreateRequest,
    PositionResponse,
    PositionUpdateRequest,
)
from .service import DepartmentService, EmployeeService, LocationService, PositionService

router = APIRouter()

# Org/employee management is HR Administrator's job (00_PROJECT_CONTEXT.md),
# so mutations are gated to it — reads are open to any authenticated org
# member (Managers/Employees plausibly need to browse the directory too).
# Not written down anywhere in 05_API_DESIGN.md yet; flagging in-code.
_ORG_STRUCTURE_WRITE_ROLES = ("hr_administrator",)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@router.post("/locations", status_code=200)
async def create_location(
    data: LocationCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> LocationResponse:
    """Create a location in the caller's organization.

    Requires the HR Administrator role.

    Args:
        data: Location fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created location.
    """
    service = LocationService(db)
    location = await service.create_location(
        caller.organization_id, caller.user_id, data.model_dump()
    )
    await db.commit()
    return LocationResponse.model_validate(location)


@router.get("/locations", status_code=200)
async def list_locations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted locations for the caller's organization.

    Open to any authenticated member of the organization.

    Args:
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of locations.
    """
    service = LocationService(db)
    result = await service.list_locations(caller.organization_id, page, limit)
    result.data = [LocationResponse.model_validate(location) for location in result.data]
    return result


@router.get("/locations/{location_id}", status_code=200)
async def get_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> LocationResponse:
    """Get a single location by id.

    Open to any authenticated member of the organization.

    Args:
        location_id: Id of the location to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping via RLS.

    Returns:
        The matching location.

    Raises:
        LocationNotFoundException: If no non-deleted location with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = LocationService(db)
    location = await service.get_location_by_id(location_id)
    return LocationResponse.model_validate(location)


@router.patch("/locations/{location_id}", status_code=200)
async def update_location(
    location_id: uuid.UUID,
    data: LocationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> LocationResponse:
    """Apply a partial update to a location.

    Requires the HR Administrator role.

    Args:
        location_id: Id of the location to update.
        data: Fields to update; unset fields are left unchanged.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated location.

    Raises:
        LocationNotFoundException: If no non-deleted location with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = LocationService(db)
    location = await service.update_location(
        location_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()
    return LocationResponse.model_validate(location)


@router.delete("/locations/{location_id}", status_code=200)
async def delete_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> LocationResponse:
    """Soft-delete a location.

    Requires the HR Administrator role.

    Args:
        location_id: Id of the location to delete.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The soft-deleted location.

    Raises:
        LocationNotFoundException: If no non-deleted location with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = LocationService(db)
    location = await service.delete_location(location_id, caller.user_id)
    await db.commit()
    return LocationResponse.model_validate(location)


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

@router.post("/departments", status_code=200)
async def create_department(
    data: DepartmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> DepartmentResponse:
    """Create a department in the caller's organization.

    Requires the HR Administrator role.

    Args:
        data: Department fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created department.
    """
    service = DepartmentService(db)
    department = await service.create_department(
        caller.organization_id, caller.user_id, data.model_dump()
    )
    await db.commit()
    return DepartmentResponse.model_validate(department)


@router.get("/departments", status_code=200)
async def list_departments(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted departments for the caller's organization.

    Open to any authenticated member of the organization.

    Args:
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of departments.
    """
    service = DepartmentService(db)
    result = await service.list_departments(caller.organization_id, page, limit)
    result.data = [DepartmentResponse.model_validate(department) for department in result.data]
    return result


@router.get("/departments/{department_id}", status_code=200)
async def get_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> DepartmentResponse:
    """Get a single department by id.

    Open to any authenticated member of the organization.

    Args:
        department_id: Id of the department to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping via RLS.

    Returns:
        The matching department.

    Raises:
        DepartmentNotFoundException: If no non-deleted department with that
            id exists in the caller's org (translates to a 404 response).
    """
    service = DepartmentService(db)
    department = await service.get_department_by_id(department_id)
    return DepartmentResponse.model_validate(department)


@router.patch("/departments/{department_id}", status_code=200)
async def update_department(
    department_id: uuid.UUID,
    data: DepartmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> DepartmentResponse:
    """Apply a partial update to a department.

    Requires the HR Administrator role.

    Args:
        department_id: Id of the department to update.
        data: Fields to update; unset fields are left unchanged.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated department.

    Raises:
        DepartmentNotFoundException: If no non-deleted department with that
            id exists in the caller's org (translates to a 404 response).
    """
    service = DepartmentService(db)
    department = await service.update_department(
        department_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()
    return DepartmentResponse.model_validate(department)


@router.delete("/departments/{department_id}", status_code=200)
async def delete_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> DepartmentResponse:
    """Soft-delete a department.

    Requires the HR Administrator role. Blocked while the department still
    has active positions assigned to it.

    Args:
        department_id: Id of the department to delete.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The soft-deleted department.

    Raises:
        DepartmentNotFoundException: If no non-deleted department with that
            id exists in the caller's org (translates to a 404 response).
        ResourceInUseException: If the department still has active positions
            assigned to it (translates to a 409 response).
    """
    service = DepartmentService(db)
    department = await service.delete_department(department_id, caller.user_id)
    await db.commit()
    return DepartmentResponse.model_validate(department)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@router.post("/positions", status_code=200)
async def create_position(
    data: PositionCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> PositionResponse:
    """Create a position in the caller's organization.

    Requires the HR Administrator role.

    Args:
        data: Position fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created position.
    """
    service = PositionService(db)
    position = await service.create_position(
        caller.organization_id, caller.user_id, data.model_dump()
    )
    await db.commit()
    return PositionResponse.model_validate(position)


@router.get("/positions", status_code=200)
async def list_positions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted positions for the caller's organization.

    Open to any authenticated member of the organization.

    Args:
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of positions.
    """
    service = PositionService(db)
    result = await service.list_positions(caller.organization_id, page, limit)
    result.data = [PositionResponse.model_validate(position) for position in result.data]
    return result


@router.get("/positions/{position_id}", status_code=200)
async def get_position(
    position_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PositionResponse:
    """Get a single position by id.

    Open to any authenticated member of the organization.

    Args:
        position_id: Id of the position to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping via RLS.

    Returns:
        The matching position.

    Raises:
        PositionNotFoundException: If no non-deleted position with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = PositionService(db)
    position = await service.get_position_by_id(position_id)
    return PositionResponse.model_validate(position)


@router.patch("/positions/{position_id}", status_code=200)
async def update_position(
    position_id: uuid.UUID,
    data: PositionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> PositionResponse:
    """Apply a partial update to a position.

    Requires the HR Administrator role.

    Args:
        position_id: Id of the position to update.
        data: Fields to update; unset fields are left unchanged.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated position.

    Raises:
        PositionNotFoundException: If no non-deleted position with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = PositionService(db)
    position = await service.update_position(
        position_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()
    return PositionResponse.model_validate(position)


@router.delete("/positions/{position_id}", status_code=200)
async def delete_position(
    position_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> PositionResponse:
    """Soft-delete a position.

    Requires the HR Administrator role. Blocked while the position still has
    active employees assigned to it or other positions reporting to it.

    Args:
        position_id: Id of the position to delete.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The soft-deleted position.

    Raises:
        PositionNotFoundException: If no non-deleted position with that id
            exists in the caller's org (translates to a 404 response).
        ResourceInUseException: If the position still has active employees
            assigned to it or positions reporting to it (translates to a
            409 response).
    """
    service = PositionService(db)
    position = await service.delete_position(position_id, caller.user_id)
    await db.commit()
    return PositionResponse.model_validate(position)


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@router.post("/employees", status_code=200)
async def create_employee(
    data: EmployeeCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> EmployeeResponse:
    """Create an employee in the caller's organization.

    Requires the HR Administrator role.

    Args:
        data: Employee fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created employee.
    """
    service = EmployeeService(db)
    employee = await service.create_employee(
        caller.organization_id, caller.user_id, data.model_dump()
    )
    await db.commit()
    return EmployeeResponse.model_validate(employee)


@router.get("/employees", status_code=200)
async def list_employees(
    location_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List non-deleted employees for the caller's organization.

    Open to any authenticated member of the organization.

    Args:
        location_id: If given, restrict results to this location.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of employees.
    """
    service = EmployeeService(db)
    result = await service.list_employees(caller.organization_id, location_id, page, limit)
    result.data = [EmployeeResponse.model_validate(employee) for employee in result.data]
    return result


@router.get("/employees/{employee_id}", status_code=200)
async def get_employee(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> EmployeeResponse:
    """Get a single employee by id.

    Open to any authenticated member of the organization.

    Args:
        employee_id: Id of the employee to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping via RLS.

    Returns:
        The matching employee.

    Raises:
        EmployeeNotFoundException: If no non-deleted employee with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = EmployeeService(db)
    employee = await service.get_employee_by_id(employee_id)
    return EmployeeResponse.model_validate(employee)


@router.patch("/employees/{employee_id}", status_code=200)
async def update_employee(
    employee_id: uuid.UUID,
    data: EmployeeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> EmployeeResponse:
    """Apply a partial update to an employee.

    Requires the HR Administrator role.

    Args:
        employee_id: Id of the employee to update.
        data: Fields to update; unset fields are left unchanged.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated employee.

    Raises:
        EmployeeNotFoundException: If no non-deleted employee with that id
            exists in the caller's org (translates to a 404 response).
    """
    service = EmployeeService(db)
    employee = await service.update_employee(
        employee_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()
    return EmployeeResponse.model_validate(employee)


@router.post("/employees/{employee_id}/offboard", status_code=200)
async def offboard_employee(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> EmployeeResponse:
    """Offboard an employee.

    Dedicated offboarding action — not a generic PATCH. Deactivates the
    employee's login access (Membership) in the same step if they have any,
    and does not block on the employee having direct reports
    (08_DECISIONS.md 2026-09-20). ``caller`` (the full Membership, not just
    its user id) is passed through so the underlying MembershipService
    guardrails apply — an HR Administrator can't offboard themselves or the
    org's Owner this way, the same protection Team Management already has.

    Requires the HR Administrator role.

    Args:
        employee_id: Id of the employee to offboard.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated, now-inactive employee.

    Raises:
        EmployeeNotFoundException: If no non-deleted employee with that id
            exists in the caller's org (translates to a 404 response).
        ValidationException: If the employee is already offboarded
            (translates to a 400 response).
    """
    service = EmployeeService(db)
    employee = await service.offboard_employee(employee_id, caller)
    await db.commit()
    return EmployeeResponse.model_validate(employee)


@router.post("/employees/{employee_id}/reinstate", status_code=200)
async def reinstate_employee(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> EmployeeResponse:
    """Reinstate a previously offboarded employee.

    Mirror of offboard_employee — reverses a termination and restores login
    access if it was deactivated by an earlier offboard.

    Requires the HR Administrator role.

    Args:
        employee_id: Id of the employee to reinstate.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated, now-active employee.

    Raises:
        EmployeeNotFoundException: If no non-deleted employee with that id
            exists in the caller's org (translates to a 404 response).
        ValidationException: If the employee is already active (translates
            to a 400 response).
    """
    service = EmployeeService(db)
    employee = await service.reinstate_employee(employee_id, caller)
    await db.commit()
    return EmployeeResponse.model_validate(employee)
