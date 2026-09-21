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
    """Capture a JSON-safe {field: value} snapshot of an ORM instance's
    current attribute values, for audit log's 'old' side of a diff."""
    return jsonable_encoder({field: getattr(instance, field, None) for field in fields})


class LocationService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = LocationRepository(db)
        self._audit = AuditService(db)

    async def create_location(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Location:
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
        location = await self._repo.get_location_by_id(location_id)
        if location is None:
            raise LocationNotFoundException()
        return location

    async def list_locations(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        return await self._repo.list_locations(organization_id, page, limit)

    async def update_location(
        self, location_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Location:
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
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = DepartmentRepository(db)
        self._audit = AuditService(db)

    async def create_department(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Department:
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
        department = await self._repo.get_department_by_id(department_id)
        if department is None:
            raise DepartmentNotFoundException()
        return department

    async def list_departments(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        return await self._repo.list_departments(organization_id, page, limit)

    async def update_department(
        self, department_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Department:
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
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = PositionRepository(db)
        self._audit = AuditService(db)

    async def create_position(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Position:
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
        position = await self._repo.get_position_by_id(position_id)
        if position is None:
            raise PositionNotFoundException()
        return position

    async def list_positions(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        return await self._repo.list_positions(organization_id, page, limit)

    async def update_position(
        self, position_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Position:
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
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = EmployeeRepository(db)
        self._audit = AuditService(db)
        self._membership_service = MembershipService(db)

    async def create_employee(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Employee:
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
        return await self._repo.list_employees(organization_id, location_id, page, limit)

    async def update_employee(
        self, employee_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Employee:
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
        """Dedicated offboarding action (08_DECISIONS.md 2026-09-20) — not a
        generic status PATCH. Sets the employee inactive and, if they have
        login access, deactivates their linked Membership in the same
        transaction. Does not block on direct reports (see the same
        decision) — informational only, logged for context.
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
        """Mirror of offboard_employee — reverses a termination (wrongful
        termination, rehire). Restores active status and re-enables login
        access if it was deactivated by an earlier offboard.
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
