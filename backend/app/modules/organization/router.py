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
    """Dedicated offboarding action — not a generic PATCH. Deactivates the
    employee's login access (Membership) in the same step if they have any,
    and does not block on the employee having direct reports (08_DECISIONS.md
    2026-09-20). caller (the full Membership, not just its user id) is
    passed through so the underlying MembershipService guardrails apply —
    an HR Administrator can't offboard themselves or the org's Owner this way,
    the same protection Team Management already has.
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
    """Mirror of offboard_employee — reverses a termination and restores
    login access if it was deactivated by an earlier offboard."""
    service = EmployeeService(db)
    employee = await service.reinstate_employee(employee_id, caller)
    await db.commit()
    return EmployeeResponse.model_validate(employee)
