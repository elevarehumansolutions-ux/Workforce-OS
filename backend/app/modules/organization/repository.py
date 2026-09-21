"""Data-access layer for the organization structure module.

Provides CRUD and lookup operations for locations, departments, positions,
and employees. Every repository operates within the caller's RLS-scoped
session and only flushes (never commits) — commits are the service layer's
responsibility.
"""

import uuid
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from .models import Location, Department, Position, Employee


class LocationRepository:
    """Handles persistence for locations within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_location(self, location: dict) -> Location:
        """Insert a new location, flush, and refresh it from the database.

        Args:
            location: Field values for the new ``Location`` row.

        Returns:
            The newly created and refreshed ``Location``.
        """
        new_location = Location(**location)
        self._db.add(new_location)
        await self._db.flush()
        await self._db.refresh(new_location)
        return new_location

    async def get_location_by_id(self, location_id: uuid.UUID) -> Location | None:
        """Get a single location by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            location_id: Id of the location to fetch.

        Returns:
            The matching non-deleted ``Location``, or ``None`` if not found.
        """
        stmt = select(Location).where(
            Location.id == location_id,
            Location.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_locations(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted locations for an organization, oldest first.

        Args:
            organization_id: Organization to list locations for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Location`` rows.
        """
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
        """Apply a partial update. Caller (service layer) commits.

        Args:
            location: The ``Location`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``Location``.
        """
        for field, value in data.items():
            setattr(location, field, value)
        await self._db.flush()
        # updated_at (server-side onupdate=func.now()) is left expired by
        # flush() alone — refresh so a later synchronous model_validate()
        # doesn't trigger a lazy-load (MissingGreenlet).
        await self._db.refresh(location)
        return location

    async def soft_delete_location(self, location: Location) -> Location:
        """Mark a location as deleted by stamping ``deleted_at``.

        Args:
            location: The ``Location`` instance to soft-delete.

        Returns:
            The soft-deleted and refreshed ``Location``.
        """
        location.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(location)
        return location


class DepartmentRepository:
    """Handles persistence for departments within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_department(self, department: dict) -> Department:
        """Insert a new department, flush, and refresh it from the database.

        Args:
            department: Field values for the new ``Department`` row.

        Returns:
            The newly created and refreshed ``Department``.
        """
        new_department = Department(**department)
        self._db.add(new_department)
        await self._db.flush()
        await self._db.refresh(new_department)
        return new_department

    async def get_department_by_id(self, department_id: uuid.UUID) -> Department | None:
        """Get a single department by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            department_id: Id of the department to fetch.

        Returns:
            The matching non-deleted ``Department``, or ``None`` if not found.
        """
        stmt = select(Department).where(
            Department.id == department_id,
            Department.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_departments(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted departments for an organization, oldest first.

        Args:
            organization_id: Organization to list departments for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Department`` rows.
        """
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
        """Apply a partial update. Caller (service layer) commits.

        Args:
            department: The ``Department`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``Department``.
        """
        for field, value in data.items():
            setattr(department, field, value)
        await self._db.flush()
        await self._db.refresh(department)
        return department

    async def soft_delete_department(self, department: Department) -> Department:
        """Mark a department as deleted by stamping ``deleted_at``.

        Args:
            department: The ``Department`` instance to soft-delete.

        Returns:
            The soft-deleted and refreshed ``Department``.
        """
        department.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(department)
        return department

    async def count_active_positions(self, department_id: uuid.UUID) -> int:
        """Count non-deleted positions still attached to this department.

        Used by the delete-blocked-while-referenced check.

        Args:
            department_id: Id of the department to count positions for.

        Returns:
            The number of matching non-deleted positions.
        """
        stmt = select(Position).where(
            Position.department_id == department_id,
            Position.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())


class PositionRepository:
    """Handles persistence for positions within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_position(self, position: dict) -> Position:
        """Insert a new position, flush, and refresh it from the database.

        Args:
            position: Field values for the new ``Position`` row.

        Returns:
            The newly created and refreshed ``Position``.
        """
        new_position = Position(**position)
        self._db.add(new_position)
        await self._db.flush()
        await self._db.refresh(new_position)
        return new_position

    async def get_position_by_id(self, position_id: uuid.UUID) -> Position | None:
        """Get a single position by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            position_id: Id of the position to fetch.

        Returns:
            The matching non-deleted ``Position``, or ``None`` if not found.
        """
        stmt = select(Position).where(
            Position.id == position_id,
            Position.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_positions(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted positions for an organization, oldest first.

        Args:
            organization_id: Organization to list positions for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Position`` rows.
        """
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
        """Apply a partial update. Caller (service layer) commits.

        Args:
            position: The ``Position`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``Position``.
        """
        for field, value in data.items():
            setattr(position, field, value)
        await self._db.flush()
        await self._db.refresh(position)
        return position

    async def soft_delete_position(self, position: Position) -> Position:
        """Mark a position as deleted by stamping ``deleted_at``.

        Args:
            position: The ``Position`` instance to soft-delete.

        Returns:
            The soft-deleted and refreshed ``Position``.
        """
        position.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(position)
        return position

    async def count_active_employees(self, position_id: uuid.UUID) -> int:
        """Count non-deleted employees still holding this position.

        Used by the delete-blocked-while-referenced check.

        Args:
            position_id: Id of the position to count employees for.

        Returns:
            The number of matching non-deleted employees.
        """
        stmt = select(Employee).where(
            Employee.position_id == position_id,
            Employee.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())

    async def count_direct_reports(self, position_id: uuid.UUID) -> int:
        """Count non-deleted positions still reporting to this one.

        Used by the delete-blocked-while-referenced check.

        Args:
            position_id: Id of the position to count direct reports for.

        Returns:
            The number of matching non-deleted positions.
        """
        stmt = select(Position).where(
            Position.reports_to_position_id == position_id,
            Position.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())


class EmployeeRepository:
    """Handles persistence for employees within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_employee(self, employee: dict) -> Employee:
        """Insert a new employee, flush, and refresh it from the database.

        Args:
            employee: Field values for the new ``Employee`` row.

        Returns:
            The newly created and refreshed ``Employee``.
        """
        new_employee = Employee(**employee)
        self._db.add(new_employee)
        await self._db.flush()
        await self._db.refresh(new_employee)
        return new_employee

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee | None:
        """Get a single employee by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            employee_id: Id of the employee to fetch.

        Returns:
            The matching non-deleted ``Employee``, or ``None`` if not found.
        """
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
        """List non-deleted employees for an organization, oldest first.

        Args:
            organization_id: Organization to list employees for.
            location_id: If given, restrict results to this location.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Employee`` rows.
        """
        stmt = select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.deleted_at.is_(None),
        )
        if location_id is not None:
            stmt = stmt.where(Employee.location_id == location_id)
        stmt = stmt.order_by(Employee.created_at.asc())
        return await paginate(stmt, page, limit, self._db)

    async def update_employee(self, employee: Employee, data: dict) -> Employee:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            employee: The ``Employee`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``Employee``.
        """
        for field, value in data.items():
            setattr(employee, field, value)
        await self._db.flush()
        await self._db.refresh(employee)
        return employee

    async def count_direct_reports(self, employee_id: uuid.UUID) -> int:
        """Count non-deleted employees who report to this employee.

        Used when offboarding — informational only, does not block the
        offboard action (see 08_DECISIONS.md 2026-09-20).

        Args:
            employee_id: Id of the manager employee to count reports for.

        Returns:
            The number of matching non-deleted direct reports.
        """
        stmt = select(Employee).where(
            Employee.manager_id == employee_id,
            Employee.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return len(result.scalars().all())
