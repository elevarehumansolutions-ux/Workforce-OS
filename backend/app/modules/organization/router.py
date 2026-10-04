"""FastAPI routes for the organization structure module.

Exposes CRUD endpoints for locations, departments, positions, and employees,
plus dedicated offboard/reinstate actions for employees. Reads are open to
any authenticated org member; mutations are gated to HR Administrator.
"""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, get_current_membership, require_org_role
from app.core.schemas import PaginationResponse
from app.core.triggers import trigger_ai_suggestion_generation
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.schemas import MembershipWithUserResponse
from app.modules.tenancy_identity.service import OrganizationService
from app.modules.tenancy_identity.tasks import dispatch_invite_email

from .schemas import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
    EmployeeCreateRequest,
    EmployeeGrantLoginRequest,
    EmployeeGrantLoginResponse,
    EmployeeLinkUserRequest,
    EmployeeResponse,
    EmployeeUpdateRequest,
    LocationCreateRequest,
    LocationResponse,
    LocationUpdateRequest,
    PositionCreateRequest,
    PositionResponse,
    PositionUpdateRequest,
)
from .models import Employee
from .service import DepartmentService, EmployeeService, LocationService, PositionService

router = APIRouter()

# Org/employee management is HR Administrator's job (00_PROJECT_CONTEXT.md),
# so mutations are gated to it — reads are open to any authenticated org
# member (Managers/Employees plausibly need to browse the directory too).
# Not written down anywhere in 05_API_DESIGN.md yet; flagging in-code.
_ORG_STRUCTURE_WRITE_ROLES = ("hr_administrator",)


async def _employee_responses(
    service: EmployeeService, employees: list[Employee]
) -> list[EmployeeResponse]:
    """Build employee responses, each with its ``invite_status`` filled in.

    One lookup for the whole batch rather than one per employee, so a page
    of the directory costs a single extra query.

    Args:
        service: The employee service, for the invite lookup.
        employees: Employees to return to the client.

    Returns:
        A response per employee, in the same order.
    """
    statuses = await service.get_invite_statuses(employees)
    responses = [EmployeeResponse.model_validate(employee) for employee in employees]
    for response in responses:
        response.invite_status = statuses.get(response.id)
    return responses


async def _employee_response(service: EmployeeService, employee: Employee) -> EmployeeResponse:
    """Build one employee response with its ``invite_status`` filled in."""
    return (await _employee_responses(service, [employee]))[0]


async def _company_name(db: AsyncSession, organization_id: uuid.UUID) -> str | None:
    """Look up the organization's name for the invite email.

    Must run before the transaction commits: the org context that row-level
    security needs is transaction-local, so it is gone afterwards.

    Args:
        db: Database session dependency.
        organization_id: Organization to look up.

    Returns:
        The organization's name, or ``None`` if it has none yet.
    """
    org = await OrganizationService(db).get_organization_by_id(organization_id)
    return org.name if org else None


def _send_employee_invite(email: str, raw_token: str, company_name: str | None) -> None:
    """Queue the invite email for an employee invited to log in.

    Call only after the transaction has committed, so the email never
    references an invite that was rolled back.

    Args:
        email: The employee's work email, the invite's recipient.
        raw_token: The invite's unhashed token, only available right after
            creation.
        company_name: Organization name to show in the email.
    """
    invite_link = f"{settings.app_url}/accept-invite?token={quote(raw_token)}"
    dispatch_invite_email.delay(email, invite_link, company_name)


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
    if department.is_critical:
        await trigger_ai_suggestion_generation(caller.organization_id)
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
    if department.is_critical:
        await trigger_ai_suggestion_generation(caller.organization_id)
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
    await trigger_ai_suggestion_generation(caller.organization_id)
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

    With ``grant_login_access`` set, the employee is also given login access
    in the same transaction: an invite email is sent to their work email, or
    their existing account is linked. Either everything happens or nothing
    does.

    Requires the HR Administrator role.

    Args:
        data: Employee fields to create, optionally with
            ``grant_login_access`` and ``role``.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created employee.

    Raises:
        UserNotFoundException: If ``user_id`` is not a member of the org
            (translates to a 404 response).
        MembershipDeactivatedException: If ``user_id``'s membership is
            deactivated (translates to a 409 response).
        EmployeeUserAlreadyLinkedException: If ``user_id`` is already linked
            to another employee (translates to a 409 response).
    """
    service = EmployeeService(db)
    fields = data.model_dump(exclude={"grant_login_access", "role"})
    raw_token = None
    company_name = None
    if not data.grant_login_access:
        employee = await service.create_employee(caller.organization_id, caller.user_id, fields)
    else:
        # SAVEPOINT: if granting login fails, the employee created a moment
        # earlier is rolled back with it, without discarding the
        # transaction-scoped RLS org context (same reasoning as the
        # business_dna upsert).
        async with db.begin_nested():
            employee = await service.create_employee(caller.organization_id, caller.user_id, fields)
            _, employee, raw_token = await service.grant_login(
                employee.id, data.role.value, caller.user_id
            )
        if raw_token is not None:
            company_name = await _company_name(db, caller.organization_id)
    await db.commit()
    if raw_token is not None:
        _send_employee_invite(employee.work_email, raw_token, company_name)
    return await _employee_response(service, employee)


@router.get("/employees/unlinked-members", status_code=200)
async def list_members_without_employee(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> PaginationResponse:
    """List active org members who have no employee record yet.

    Feeds the "link an existing member" picker on Add Employee and the
    link-user action. Declared before ``/employees/{employee_id}`` so the
    path isn't read as an employee id.

    Requires the HR Administrator role.

    Args:
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        A paginated response of memberships, each paired with its user.
    """
    service = EmployeeService(db)
    result = await service.list_members_without_employee(caller.organization_id, page, limit)
    result.data = [MembershipWithUserResponse.model_validate(m) for m in result.data]
    return result


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
    result.data = await _employee_responses(service, result.data)
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
    return await _employee_response(service, employee)


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
    return await _employee_response(service, employee)


@router.post("/employees/{employee_id}/link-user", status_code=200)
async def link_employee_user(
    employee_id: uuid.UUID,
    data: EmployeeLinkUserRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> EmployeeResponse:
    """Link an existing org member's login to an employee that has none.

    Dedicated action — not a PATCH field. One-way: a linked login can't be
    cleared or swapped, because offboarding finds the login to deactivate
    through it. The user must be an active member of the org and not
    already linked to another employee.

    Requires the HR Administrator role.

    Args:
        employee_id: Id of the employee to link.
        data: The ``user_id`` to link.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated employee.

    Raises:
        EmployeeNotFoundException: If no non-deleted employee with that id
            exists in the caller's org (translates to a 404 response).
        EmployeeAlreadyHasLoginException: If the employee already has a
            login (translates to a 409 response).
        UserNotFoundException: If the user isn't a member of the org
            (translates to a 404 response).
        MembershipDeactivatedException: If the user's membership is
            deactivated (translates to a 409 response).
        EmployeeUserAlreadyLinkedException: If the user is already linked
            to another employee (translates to a 409 response).
    """
    service = EmployeeService(db)
    employee = await service.link_user(employee_id, data.user_id, caller.user_id)
    await db.commit()
    return await _employee_response(service, employee)


@router.post("/employees/{employee_id}/grant-login", status_code=200)
async def grant_employee_login(
    employee_id: uuid.UUID,
    data: EmployeeGrantLoginRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_ORG_STRUCTURE_WRITE_ROLES)),
) -> EmployeeGrantLoginResponse:
    """Give an employee login access ("Send invite"), or resend the invite.

    Uses the employee's work email. If an existing account or org member
    has it, the employee is linked straight away; otherwise an invite email
    is sent, and accepting it links the new account to this employee.
    Calling it again before the invite is accepted replaces the pending
    invite with a fresh one (the old link stops working), so this is also
    the resend action.

    Requires the HR Administrator role.

    Args:
        employee_id: Id of the employee to give login access.
        data: The ``role`` to grant.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The outcome (``invited``, ``added`` or ``linked``) and the employee.

    Raises:
        EmployeeNotFoundException: If no non-deleted employee with that id
            exists in the caller's org (translates to a 404 response).
        EmployeeAlreadyHasLoginException: If the employee already has a
            login (translates to a 409 response).
        ValidationException: If the employee is offboarded (translates to
            a 422 response).
    """
    service = EmployeeService(db)
    outcome, employee, raw_token = await service.grant_login(
        employee_id, data.role.value, caller.user_id
    )
    company_name = (
        await _company_name(db, caller.organization_id) if raw_token is not None else None
    )
    await db.commit()
    if raw_token is not None:
        _send_employee_invite(employee.work_email, raw_token, company_name)
    return EmployeeGrantLoginResponse(
        outcome=outcome, employee=await _employee_response(service, employee)
    )


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
    return await _employee_response(service, employee)


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
    return await _employee_response(service, employee)
