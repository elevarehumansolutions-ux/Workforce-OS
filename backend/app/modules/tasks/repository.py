"""Data-access layer for the Task module."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse

from .enums import TaskStatus
from .models import Task

# The atomic complete relies on RETURNING for the truth about what changed.
# synchronize_session=False stops SQLAlchemy guessing in Python which loaded
# objects the WHERE clause matched; populate_existing=True makes the returned
# row refresh any copy already loaded. Same options as the attendance and AI
# modules' atomic UPDATEs.
_ATOMIC_UPDATE_OPTIONS = {"synchronize_session": False, "populate_existing": True}

_OPEN_STATUSES = (TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value)


@dataclass(frozen=True)
class TaskScope:
    """Which tasks a caller may see.

    HR administrators and business executives see every task in the
    organization. Everyone else sees a task if it is assigned to them, they
    created it, or it belongs to a department they head (or, for the
    ``manager`` role, their own department).

    Attributes:
        sees_all: True for roles with an organization-wide view.
        user_id: The caller's user id, to match ``created_by_user_id``.
        employee_id: The caller's employee id, or ``None`` if they have no
            employee record.
        department_ids: Departments whose tasks the caller may see.
    """

    sees_all: bool
    user_id: uuid.UUID
    employee_id: uuid.UUID | None
    department_ids: frozenset[uuid.UUID]

    def allows(self, task: Task) -> bool:
        """Whether this caller may see ``task``."""
        if self.sees_all:
            return True
        return (
            (self.employee_id is not None and task.assigned_to_employee_id == self.employee_id)
            or task.created_by_user_id == self.user_id
            or task.department_id in self.department_ids
        )


class TaskRepository:
    """Handles persistence for tasks within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_task(self, task: dict) -> Task:
        """Insert a new task, flush, and refresh it from the database.

        Args:
            task: Field values for the new ``Task`` row.

        Returns:
            The newly created and refreshed ``Task``.
        """
        new_task = Task(**task)
        self._db.add(new_task)
        await self._db.flush()
        await self._db.refresh(new_task)
        return new_task

    async def get_task_by_id(self, task_id: uuid.UUID) -> Task | None:
        """Get a single non-deleted task by its own id.

        RLS already restricts this to the caller's current org. Whether the
        caller may *see* it within the org is the service's job (``TaskScope``).

        Args:
            task_id: Id of the task to fetch.

        Returns:
            The matching ``Task``, or ``None`` if not found.
        """
        stmt = select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        scope: TaskScope,
        department_id: uuid.UUID | None = None,
        assigned_to_employee_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        kpi_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the tasks a caller may see, newest first, with optional filters.

        Args:
            scope: Which tasks the caller may see.
            department_id: Only tasks for this department.
            assigned_to_employee_id: Only tasks assigned to this employee.
            status: Only tasks in this status.
            kpi_id: Only tasks linked to this KPI.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Task`` rows.
        """
        stmt = select(Task).where(Task.deleted_at.is_(None))
        if not scope.sees_all:
            visible = [Task.created_by_user_id == scope.user_id]
            if scope.employee_id is not None:
                visible.append(Task.assigned_to_employee_id == scope.employee_id)
            if scope.department_ids:
                visible.append(Task.department_id.in_(scope.department_ids))
            stmt = stmt.where(or_(*visible))
        if department_id is not None:
            stmt = stmt.where(Task.department_id == department_id)
        if assigned_to_employee_id is not None:
            stmt = stmt.where(Task.assigned_to_employee_id == assigned_to_employee_id)
        if status is not None:
            stmt = stmt.where(Task.status == status.value)
        if kpi_id is not None:
            stmt = stmt.where(Task.kpi_id == kpi_id)
        stmt = stmt.order_by(Task.created_at.desc(), Task.id)
        return await paginate(stmt, page, limit, self._db)

    async def update_task(self, task: Task, data: dict) -> Task:
        """Apply a partial update to a task. Caller (service layer) commits.

        Args:
            task: The ``Task`` instance to update.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``Task``.
        """
        for field, value in data.items():
            setattr(task, field, value)
        await self._db.flush()
        await self._db.refresh(task)
        return task

    async def complete_task(self, task_id: uuid.UUID, completed_at: datetime) -> Task | None:
        """Atomically complete a task, but only if it is still open or in progress.

        The "still open?" check is part of the UPDATE itself, so two people
        completing the same task at once can't both succeed and the first
        completion time stands.

        Args:
            task_id: Id of the task to complete.
            completed_at: The completion moment.

        Returns:
            The completed ``Task``, or ``None`` if nothing changed (it was
            already completed or cancelled, or doesn't exist).
        """
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.deleted_at.is_(None),
                Task.status.in_(_OPEN_STATUSES),
            )
            .values(status=TaskStatus.COMPLETED.value, completed_at=completed_at)
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()
