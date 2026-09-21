"""Business logic for the organization structure module.

Each service wraps its matching repository, adding not-found checks,
delete-blocked-while-referenced guards, and audit logging around plain CRUD.
Services flush via the repository but never commit — the router commits
after a successful call.
"""

import uuid

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DepartmentNotFoundException,
    EmployeeNotFoundException,
    LocationNotFoundException,
    PositionNotFoundException,
    ResourceInUseException,
    ValidationException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.service import AuditService
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.service import MembershipService

from .enums import EmployeeStatus
from .models import Department, Employee, Location, Position
from .repository import DepartmentRepository, EmployeeRepository, LocationRepository, PositionRepository


def _snapshot(instance, fields) -> dict:
    """Capture a JSON-safe snapshot of an ORM instance's current values.

    Used for the audit log's 'old' side of a before/after diff.

    Args:
        instance: The ORM instance to read attribute values from.
        fields: Names of the attributes/columns to include.

    Returns:
        A JSON-encodable dict mapping each field name to its current value.
    """
    return jsonable_encoder({field: getattr(instance, field, None) for field in fields})


class LocationService:
    """Business logic for creating, reading, updating, and deleting locations."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = LocationRepository(db)
        self._audit = AuditService(db)

    async def create_location(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Location:
        """Create a location for an organization and record an audit entry.

        Args:
            organization_id: Organization the new location belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new location.

        Returns:
            The newly created ``Location``.
        """
        location = await self._repo.create_location({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="location",
            entity_id=location.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return location

    async def get_location_by_id(self, location_id: uuid.UUID) -> Location:
        """Fetch a location by id.

        Args:
            location_id: Id of the location to fetch.

        Returns:
            The matching ``Location``.

        Raises:
            LocationNotFoundException: If no non-deleted location with that
                id exists in the caller's org.
        """
        location = await self._repo.get_location_by_id(location_id)
        if location is None:
            raise LocationNotFoundException()
        return location

    async def list_locations(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted locations for an organization.

        Args:
            organization_id: Organization to list locations for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Location`` rows.
        """
        return await self._repo.list_locations(organization_id, page, limit)

    async def update_location(
        self, location_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Location:
        """Apply a partial update to a location and record an audit entry.

        Args:
            location_id: Id of the location to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Location``.

        Raises:
            LocationNotFoundException: If no non-deleted location with that
                id exists in the caller's org.
        """
        location = await self.get_location_by_id(location_id)
        old_data = _snapshot(location, data.keys())
        location = await self._repo.update_location(location, data)
        await self._audit.log_action(
            organization_id=location.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="location",
            entity_id=location.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return location

    async def delete_location(self, location_id: uuid.UUID, actor_user_id: uuid.UUID) -> Location:
        """Soft-delete a location and record an audit entry.

        Args:
            location_id: Id of the location to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``Location``.

        Raises:
            LocationNotFoundException: If no non-deleted location with that
                id exists in the caller's org.
        """
        location = await self.get_location_by_id(location_id)
        old_data = _snapshot(location, Location.__table__.columns.keys())
        location = await self._repo.soft_delete_location(location)
        await self._audit.log_action(
            organization_id=location.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="location",
            entity_id=location.id,
            changes={"old": old_data, "new": None},
        )
        return location


class DepartmentService:
    """Business logic for creating, reading, updating, and deleting departments."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = DepartmentRepository(db)
        self._audit = AuditService(db)

    async def create_department(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Department:
        """Create a department for an organization and record an audit entry.

        Args:
            organization_id: Organization the new department belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new department.

        Returns:
            The newly created ``Department``.
        """
        department = await self._repo.create_department({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="department",
            entity_id=department.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return department

    async def get_department_by_id(self, department_id: uuid.UUID) -> Department:
        """Fetch a department by id.

        Args:
            department_id: Id of the department to fetch.

        Returns:
            The matching ``Department``.

        Raises:
            DepartmentNotFoundException: If no non-deleted department with
                that id exists in the caller's org.
        """
        department = await self._repo.get_department_by_id(department_id)
        if department is None:
            raise DepartmentNotFoundException()
        return department

    async def list_departments(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted departments for an organization.

        Args:
            organization_id: Organization to list departments for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Department`` rows.
        """
        return await self._repo.list_departments(organization_id, page, limit)

    async def update_department(
        self, department_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Department:
        """Apply a partial update to a department and record an audit entry.

        Args:
            department_id: Id of the department to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Department``.

        Raises:
            DepartmentNotFoundException: If no non-deleted department with
                that id exists in the caller's org.
        """
        department = await self.get_department_by_id(department_id)
        old_data = _snapshot(department, data.keys())
        department = await self._repo.update_department(department, data)
        await self._audit.log_action(
            organization_id=department.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="department",
            entity_id=department.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return department

    async def delete_department(self, department_id: uuid.UUID, actor_user_id: uuid.UUID) -> Department:
        """Soft-delete a department, blocking while it still has active positions.

        Deletion is blocked-while-referenced rather than cascaded
        (01_REQUIREMENTS.md §2, 08_DECISIONS.md 2026-09-07).

        Args:
            department_id: Id of the department to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``Department``.

        Raises:
            DepartmentNotFoundException: If no non-deleted department with
                that id exists in the caller's org.
            ResourceInUseException: If the department still has active
                positions assigned to it.
        """
        # Blocked-while-referenced, not cascaded (01_REQUIREMENTS.md §2,
        # 08_DECISIONS.md 2026-09-07) — named reason, no silent allow.
        department = await self.get_department_by_id(department_id)

        active_positions = await self._repo.count_active_positions(department_id)
        if active_positions > 0:
            raise ResourceInUseException(
                message=f"Cannot delete department: {active_positions} active position(s) still assigned"
            )

        old_data = _snapshot(department, Department.__table__.columns.keys())
        department = await self._repo.soft_delete_department(department)
        await self._audit.log_action(
            organization_id=department.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="department",
            entity_id=department.id,
            changes={"old": old_data, "new": None},
        )
        return department


class PositionService:
    """Business logic for creating, reading, updating, and deleting positions."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = PositionRepository(db)
        self._audit = AuditService(db)

    async def create_position(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Position:
        """Create a position for an organization and record an audit entry.

        Args:
            organization_id: Organization the new position belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new position.

        Returns:
            The newly created ``Position``.
        """
        position = await self._repo.create_position({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="position",
            entity_id=position.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return position

    async def get_position_by_id(self, position_id: uuid.UUID) -> Position:
        """Fetch a position by id.

        Args:
            position_id: Id of the position to fetch.

        Returns:
            The matching ``Position``.

        Raises:
            PositionNotFoundException: If no non-deleted position with that
                id exists in the caller's org.
        """
        position = await self._repo.get_position_by_id(position_id)
        if position is None:
            raise PositionNotFoundException()
        return position

    async def list_positions(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted positions for an organization.

        Args:
            organization_id: Organization to list positions for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Position`` rows.
        """
        return await self._repo.list_positions(organization_id, page, limit)

    async def update_position(
        self, position_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Position:
        """Apply a partial update to a position and record an audit entry.

        Args:
            position_id: Id of the position to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Position``.

        Raises:
            PositionNotFoundException: If no non-deleted position with that
                id exists in the caller's org.
        """
        position = await self.get_position_by_id(position_id)
        old_data = _snapshot(position, data.keys())
        position = await self._repo.update_position(position, data)
        await self._audit.log_action(
            organization_id=position.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="position",
            entity_id=position.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return position

    async def delete_position(self, position_id: uuid.UUID, actor_user_id: uuid.UUID) -> Position:
        """Soft-delete a position, blocking while it is still referenced.

        Blocked-while-referenced against two independent references: active
        employees holding this position, and other positions reporting to
        it. Both are checked and reported together in a single error.

        Args:
            position_id: Id of the position to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``Position``.

        Raises:
            PositionNotFoundException: If no non-deleted position with that
                id exists in the caller's org.
            ResourceInUseException: If the position still has active
                employees assigned to it or positions reporting to it.
        """
        # Same blocked-while-referenced rule as DepartmentService.delete_department,
        # checked against two independent references (active employees holding
        # this position, other positions reporting to it) and reported together.
        position = await self.get_position_by_id(position_id)

        active_employees = await self._repo.count_active_employees(position_id)
        direct_reports = await self._repo.count_direct_reports(position_id)
        reasons = []
        if active_employees > 0:
            reasons.append(f"{active_employees} active employee(s) still assigned")
        if direct_reports > 0:
            reasons.append(f"{direct_reports} position(s) still reporting to it")
        if reasons:
            raise ResourceInUseException(message=f"Cannot delete position: {'; '.join(reasons)}")

        old_data = _snapshot(position, Position.__table__.columns.keys())
        position = await self._repo.soft_delete_position(position)
        await self._audit.log_action(
            organization_id=position.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="position",
            entity_id=position.id,
            changes={"old": old_data, "new": None},
        )
        return position


class EmployeeService:
    """Business logic for creating, reading, updating, offboarding, and reinstating employees."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = EmployeeRepository(db)
        self._audit = AuditService(db)
        self._membership_service = MembershipService(db)

    async def create_employee(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Employee:
        """Create an employee for an organization and record an audit entry.

        Args:
            organization_id: Organization the new employee belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new employee.

        Returns:
            The newly created ``Employee``.
        """
        employee = await self._repo.create_employee({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="employee",
            entity_id=employee.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return employee

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee:
        """Fetch an employee by id.

        Args:
            employee_id: Id of the employee to fetch.

        Returns:
            The matching ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
        """
        employee = await self._repo.get_employee_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundException()
        return employee

    async def list_employees(
        self,
        organization_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted employees for an organization.

        Args:
            organization_id: Organization to list employees for.
            location_id: If given, restrict results to this location.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Employee`` rows.
        """
        return await self._repo.list_employees(organization_id, location_id, page, limit)

    async def update_employee(
        self, employee_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Employee:
        """Apply a partial update to an employee and record an audit entry.

        Args:
            employee_id: Id of the employee to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
        """
        employee = await self.get_employee_by_id(employee_id)
        old_data = _snapshot(employee, data.keys())
        employee = await self._repo.update_employee(employee, data)
        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="employee",
            entity_id=employee.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return employee

    async def offboard_employee(self, employee_id: uuid.UUID, caller: Membership) -> Employee:
        """Offboard an employee: set them inactive and deactivate their login.

        Dedicated offboarding action (08_DECISIONS.md 2026-09-20), not a
        generic status PATCH. If the employee has login access, deactivates
        their linked ``Membership`` in the same transaction, going through
        ``MembershipService.update_membership`` so its guardrails apply (an
        HR Administrator can't offboard themselves or the org's Owner this
        way). Does not block on the employee having direct reports (same
        decision) — that count is informational only, logged for context.

        Args:
            employee_id: Id of the employee to offboard.
            caller: The acting membership; passed through so
                ``MembershipService`` guardrails apply when deactivating a
                linked membership.

        Returns:
            The updated, now-inactive ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
            ValidationException: If the employee is already offboarded.
        """
        employee = await self.get_employee_by_id(employee_id)
        if employee.status == EmployeeStatus.INACTIVE.value:
            raise ValidationException(message="Employee is already offboarded")

        old_status = employee.status
        employee = await self._repo.update_employee(employee, {"status": EmployeeStatus.INACTIVE.value})

        membership_deactivated = False
        if employee.user_id is not None:
            membership = await self._membership_service.get_membership(
                employee.user_id, employee.organization_id
            )
            if membership is not None and membership.deactivated_at is None:
                await self._membership_service.update_membership(
                    target=membership, caller=caller, role=None, is_deactivated=True
                )
                membership_deactivated = True

        direct_reports = await self._repo.count_direct_reports(employee_id)
        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=caller.user_id,
            action="offboard",
            entity_type="employee",
            entity_id=employee.id,
            changes={
                "old": {"status": old_status},
                "new": {"status": employee.status},
                "membership_deactivated": membership_deactivated,
                "direct_reports_at_time": direct_reports,
            },
        )
        return employee

    async def reinstate_employee(self, employee_id: uuid.UUID, caller: Membership) -> Employee:
        """Reinstate a previously offboarded employee.

        Mirror of ``offboard_employee`` — reverses a termination (wrongful
        termination, rehire). Restores active status and re-enables login
        access if it was deactivated by an earlier offboard.

        Args:
            employee_id: Id of the employee to reinstate.
            caller: The acting membership; passed through so
                ``MembershipService`` guardrails apply when reactivating a
                linked membership.

        Returns:
            The updated, now-active ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
            ValidationException: If the employee is already active.
        """
        employee = await self.get_employee_by_id(employee_id)
        if employee.status == EmployeeStatus.ACTIVE.value:
            raise ValidationException(message="Employee is already active")

        old_status = employee.status
        employee = await self._repo.update_employee(employee, {"status": EmployeeStatus.ACTIVE.value})

        membership_reactivated = False
        if employee.user_id is not None:
            membership = await self._membership_service.get_membership(
                employee.user_id, employee.organization_id
            )
            if membership is not None and membership.deactivated_at is not None:
                await self._membership_service.update_membership(
                    target=membership, caller=caller, role=None, is_deactivated=False
                )
                membership_reactivated = True

        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=caller.user_id,
            action="reinstate",
            entity_type="employee",
            entity_id=employee.id,
            changes={
                "old": {"status": old_status},
                "new": {"status": employee.status},
                "membership_reactivated": membership_reactivated,
            },
        )
        return employee
