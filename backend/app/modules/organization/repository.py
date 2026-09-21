import uuid
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from .models import Location, Department, Position, Employee


class LocationRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_location(self, location: dict) -> Location:
        new_location = Location(**location)
        self._db.add(new_location)
        await self._db.flush()
        await self._db.refresh(new_location)
        return new_location

    async def get_location_by_id(self, location_id: uuid.UUID) -> Location | None:
        """Get a single location by its own id (RLS already restricts this
        to the caller's current org)."""
        stmt = select(Location).where(
            Location.id == location_id,
            Location.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_locations(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        stmt = (
            select(Location)
            .where(
                Location.organization_id == organization_id,
                Location.deleted_at.is_(None),
            )
            .order_by(Location.created_at.asc())
        )
        return await paginate(stmt, page, limit, self._db)

    async def update_location(self, location: Location, data: dict) -> Location:
        """Apply a partial update. Caller (service layer) commits."""
        for field, value in data.items():
            setattr(location, field, value)
        await self._db.flush()
        # updated_at (server-side onupdate=func.now()) is left expired by
        # flush() alone — refresh so a later synchronous model_validate()
        # doesn't trigger a lazy-load (MissingGreenlet).
        await self._db.refresh(location)
        return location

    async def soft_delete_location(self, location: Location) -> Location:
        location.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(location)
        return location


class DepartmentRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_department(self, department: dict) -> Department:
        new_department = Department(**department)
        self._db.add(new_department)
        await self._db.flush()
        await self._db.refresh(new_department)
        return new_department

    async def get_department_by_id(self, department_id: uuid.UUID) -> Department | None:
        """Get a single department by its own id (RLS already restricts
        this to the caller's current org)."""
        stmt = select(Department).where(
            Department.id == department_id,
            Department.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_departments(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        stmt = (
            select(Department)
            .where(
                Department.organization_id == organization_id,
                Department.deleted_at.is_(None),
            )
            .order_by(Department.created_at.asc())
        )
        return await paginate(stmt, page, limit, self._db)

    async def update_department(self, department: Department, data: dict) -> Department:
        """Apply a partial update. Caller (service layer) commits."""
        for field, value in data.items():
            setattr(department, field, value)
        await self._db.flush()
        await self._db.refresh(department)
        return department

    async def soft_delete_department(self, department: Department) -> Department:
        department.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(department)
        return department

    async def count_active_positions(self, department_id: uuid.UUID) -> int:
        """Used by the delete-blocked-while-referenced check — counts
        non-deleted positions still attached to this department."""
        stmt = select(Position).where(
            Position.department_id == department_id,
            Position.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())


class PositionRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_position(self, position: dict) -> Position:
        new_position = Position(**position)
        self._db.add(new_position)
        await self._db.flush()
        await self._db.refresh(new_position)
        return new_position

    async def get_position_by_id(self, position_id: uuid.UUID) -> Position | None:
        """Get a single position by its own id (RLS already restricts this
        to the caller's current org)."""
        stmt = select(Position).where(
            Position.id == position_id,
            Position.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_positions(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        stmt = (
            select(Position)
            .where(
                Position.organization_id == organization_id,
                Position.deleted_at.is_(None),
            )
            .order_by(Position.created_at.asc())
        )
        return await paginate(stmt, page, limit, self._db)

    async def update_position(self, position: Position, data: dict) -> Position:
        """Apply a partial update. Caller (service layer) commits."""
        for field, value in data.items():
            setattr(position, field, value)
        await self._db.flush()
        await self._db.refresh(position)
        return position

    async def soft_delete_position(self, position: Position) -> Position:
        position.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(position)
        return position

    async def count_active_employees(self, position_id: uuid.UUID) -> int:
        """Used by the delete-blocked-while-referenced check — counts
        non-deleted employees still holding this position."""
        stmt = select(Employee).where(
            Employee.position_id == position_id,
            Employee.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())

    async def count_direct_reports(self, position_id: uuid.UUID) -> int:
        """Used by the delete-blocked-while-referenced check — counts
        non-deleted positions still reporting to this one."""
        stmt = select(Position).where(
            Position.reports_to_position_id == position_id,
            Position.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())


class EmployeeRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_employee(self, employee: dict) -> Employee:
        new_employee = Employee(**employee)
        self._db.add(new_employee)
        await self._db.flush()
        await self._db.refresh(new_employee)
        return new_employee

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee | None:
        """Get a single employee by its own id (RLS already restricts this
        to the caller's current org)."""
        stmt = select(Employee).where(
            Employee.id == employee_id,
            Employee.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_employees(
        self,
        organization_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        stmt = select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.deleted_at.is_(None),
        )
        if location_id is not None:
            stmt = stmt.where(Employee.location_id == location_id)
        stmt = stmt.order_by(Employee.created_at.asc())
        return await paginate(stmt, page, limit, self._db)

    async def update_employee(self, employee: Employee, data: dict) -> Employee:
        """Apply a partial update. Caller (service layer) commits."""
        for field, value in data.items():
            setattr(employee, field, value)
        await self._db.flush()
        await self._db.refresh(employee)
        return employee

    async def count_direct_reports(self, employee_id: uuid.UUID) -> int:
        """Used when offboarding — informational only, does not block the
        offboard action (see 08_DECISIONS.md 2026-09-20)."""
        stmt = select(Employee).where(
            Employee.manager_id == employee_id,
            Employee.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())
