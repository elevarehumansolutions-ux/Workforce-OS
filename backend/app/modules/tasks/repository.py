"""Data-access layer for the Task module."""

import uuid
from datetime import datetime

from sqlalchemy import false, func, not_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from app.modules.organization.enums import EmployeeStatus
from app.modules.organization.models import Employee

from .enums import OPEN_STATUSES, ReviewStatus, TaskStatus
from .models import Task, TaskBlock
from .overdue import overdue_clause

# The atomic complete relies on RETURNING for the truth about what changed.
# synchronize_session=False stops SQLAlchemy guessing in Python which loaded
# objects the WHERE clause matched; populate_existing=True makes the returned
# row refresh any copy already loaded. Same options as the attendance and AI
# modules' atomic UPDATEs.
_ATOMIC_UPDATE_OPTIONS = {"synchronize_session": False, "populate_existing": True}


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
            employee record (or aren't clocked in, see the service).
        department_ids: A list of departments whose tasks the caller may see.
    """

    def __init__(
        self,
        sees_all: bool,
        user_id: uuid.UUID,
        employee_id: uuid.UUID | None,
        department_ids: list[uuid.UUID],
    ):
        """Store who the caller is and what they are allowed to see."""
        self.sees_all = sees_all
        self.user_id = user_id
        self.employee_id = employee_id
        self.department_ids = department_ids

    def allows(self, task: Task) -> bool:
        """Whether this caller may see ``task``."""
        if self.sees_all:
            return True
        if self.employee_id is not None and task.assigned_to_employee_id == self.employee_id:
            return True  # it is assigned to me
        if task.created_by_user_id == self.user_id:
            return True  # I created it
        if task.department_id in self.department_ids:
            return True  # it belongs to a department I look after
        return False


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
        overdue: bool | None = None,
        now: datetime | None = None,
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
            overdue: True for only overdue tasks, False for only tasks that
                are not overdue, None for both.
            now: The moment "overdue" is judged against. Required when
                ``overdue`` is given.

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
        if overdue is True:
            stmt = stmt.where(overdue_clause(now))
        elif overdue is False:
            stmt = stmt.where(not_(overdue_clause(now)))
        stmt = stmt.order_by(Task.created_at.desc(), Task.id)
        return await paginate(stmt, page, limit, self._db)

    async def count_completed_tasks_for_kpi(
        self, kpi_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> int:
        """Count the tasks linked to a KPI that were completed within a period.

        Only ``completed`` tasks count: open, blocked and cancelled ones do
        not. The period includes ``period_start`` and excludes ``period_end``.
        Not limited to what a particular caller may see: it is a total for the
        KPI (like the KPI itself, which every member can read), and RLS still
        keeps it inside the caller's organization.

        Args:
            kpi_id: The KPI.
            period_start: The first moment counted.
            period_end: The first moment NOT counted.

        Returns:
            How many tasks.
        """
        stmt = select(func.count()).select_from(Task).where(
            Task.kpi_id == kpi_id,
            Task.deleted_at.is_(None),
            Task.status == TaskStatus.COMPLETED.value,
            Task.completed_at >= period_start,
            Task.completed_at < period_end,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

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
        # A new deadline gets its own "overdue" alert, so forget the old one.
        if "due_at" in data:
            task.overdue_notified_at = None
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
                Task.status.in_(OPEN_STATUSES),
            )
            .values(status=TaskStatus.COMPLETED.value, completed_at=completed_at)
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def mark_task_blocked(self, task_id: uuid.UUID, now: datetime) -> Task | None:
        """Atomically mark a task blocked, but only if it is open and not already blocked.

        One UPDATE does the check and the change, so two people blocking the
        same task at once can't both succeed.

        Args:
            task_id: Id of the task.
            now: The moment the block starts.

        Returns:
            The updated ``Task``, or ``None`` if nothing changed (it is
            completed, cancelled, already blocked, or doesn't exist).
        """
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_STATUSES),
                Task.blocked_since.is_(None),
            )
            .values(blocked_since=now)
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def create_block(self, block: dict) -> TaskBlock:
        """Insert a new block row, flush, and refresh it from the database.

        Args:
            block: Field values for the new ``TaskBlock``.

        Returns:
            The newly created ``TaskBlock``.
        """
        new_block = TaskBlock(**block)
        self._db.add(new_block)
        await self._db.flush()
        await self._db.refresh(new_block)
        return new_block

    async def get_open_block(self, task_id: uuid.UUID) -> TaskBlock | None:
        """Get the task's current block (the one with no ``unblocked_at``), if any."""
        stmt = select(TaskBlock).where(
            TaskBlock.task_id == task_id,
            TaskBlock.unblocked_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_blocks_for_task(self, task_id: uuid.UUID) -> list[TaskBlock]:
        """List every block a task has had, newest first."""
        stmt = (
            select(TaskBlock)
            .where(TaskBlock.task_id == task_id)
            .order_by(TaskBlock.blocked_at.desc(), TaskBlock.id)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def close_block(self, block_id: uuid.UUID, now: datetime) -> TaskBlock | None:
        """Atomically end a block, but only if it is still open.

        Args:
            block_id: Id of the block.
            now: The moment the block ends.

        Returns:
            The closed ``TaskBlock``, or ``None`` if it was already closed.
        """
        stmt = (
            update(TaskBlock)
            .where(TaskBlock.id == block_id, TaskBlock.unblocked_at.is_(None))
            .values(unblocked_at=now)
            .returning(TaskBlock)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def get_block_by_id(self, block_id: uuid.UUID) -> TaskBlock | None:
        """Get one block by its id (RLS already limits it to the caller's organization)."""
        result = await self._db.execute(select(TaskBlock).where(TaskBlock.id == block_id))
        return result.scalar_one_or_none()

    async def get_tasks_by_ids(self, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, Task]:
        """Get several tasks at once, as a dictionary from task id to task."""
        if not task_ids:
            return {}
        result = await self._db.execute(select(Task).where(Task.id.in_(task_ids)))
        return {task.id: task for task in result.scalars().all()}

    async def list_blocks_for_review(
        self,
        reviewer_user_id: uuid.UUID,
        sees_all: bool,
        department_ids: list[uuid.UUID],
        manager_employee_id: uuid.UUID | None,
        review_status: ReviewStatus | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the blocks a reviewer is allowed to review, newest first.

        This is the database form of the rule "who may review a block"
        (the Python form is ``TaskService._can_review``; a test keeps them in
        step). A block is reviewable by HR (``sees_all``), by the head of its
        task's department, or by the blocker's own reporting manager, and
        never by the person who recorded it.

        Args:
            reviewer_user_id: The reviewer's user id (their own blocks are left out).
            sees_all: True for HR administrators.
            department_ids: Departments the reviewer heads.
            manager_employee_id: The reviewer's employee id, to find the people
                who report to them; ``None`` if they have no employee record.
            review_status: Only blocks in this state (``None`` for all).
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``TaskBlock`` rows.
        """
        stmt = select(TaskBlock).join(Task, Task.id == TaskBlock.task_id)
        stmt = stmt.where(TaskBlock.blocked_by_user_id != reviewer_user_id)
        if not sees_all:
            conditions = []
            if department_ids:
                conditions.append(Task.department_id.in_(department_ids))
            if manager_employee_id is not None:
                my_reports = select(Employee.user_id).where(
                    Employee.manager_id == manager_employee_id,
                    Employee.user_id.is_not(None),
                )
                conditions.append(TaskBlock.blocked_by_user_id.in_(my_reports))
            if conditions:
                stmt = stmt.where(or_(*conditions))
            else:
                stmt = stmt.where(false())  # not a head, not anyone's manager: nothing to review
        if review_status is not None:
            stmt = stmt.where(TaskBlock.review_status == review_status.value)
        stmt = stmt.order_by(TaskBlock.blocked_at.desc(), TaskBlock.id)
        return await paginate(stmt, page, limit, self._db)

    async def review_block(
        self,
        block_id: uuid.UUID,
        decision: ReviewStatus,
        reviewer_user_id: uuid.UUID,
        now: datetime,
    ) -> TaskBlock | None:
        """Atomically approve or reject a block, but only if it is still pending.

        Args:
            block_id: Id of the block.
            decision: ``APPROVED`` or ``REJECTED``.
            reviewer_user_id: Who is deciding.
            now: The moment of the decision.

        Returns:
            The reviewed ``TaskBlock``, or ``None`` if it was not pending any more.
        """
        stmt = (
            update(TaskBlock)
            .where(
                TaskBlock.id == block_id,
                TaskBlock.review_status == ReviewStatus.PENDING.value,
            )
            .values(
                review_status=decision.value,
                reviewed_by_user_id=reviewer_user_id,
                reviewed_at=now,
            )
            .returning(TaskBlock)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def add_approved_seconds(self, task_id: uuid.UUID, seconds: int) -> None:
        """Add approved blocked time to a task's running total.

        The effective deadline moves later, so the "overdue" alert is allowed
        to fire again for the new moment.
        """
        await self._db.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                approved_blocked_seconds=Task.approved_blocked_seconds + seconds,
                overdue_notified_at=None,
            )
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        await self._db.flush()

    async def clear_blocked_state(self, task_id: uuid.UUID, approved_seconds_to_add: int) -> None:
        """Mark a task as no longer blocked, crediting any approved blocked time.

        Called when a block ends. ``approved_seconds_to_add`` is 0 unless the
        block was already approved. Credited time moves the effective deadline,
        so the "overdue" alert is allowed to fire again for the new moment.

        Args:
            task_id: Id of the task.
            approved_seconds_to_add: Blocked seconds to add to the running total.
        """
        values = {"blocked_since": None}
        if approved_seconds_to_add > 0:
            values["approved_blocked_seconds"] = Task.approved_blocked_seconds + approved_seconds_to_add
            values["overdue_notified_at"] = None
        await self._db.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(**values)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        await self._db.flush()

    async def list_organizations_needing_scan(self) -> list[uuid.UUID]:
        """List every organization the task scan should look at.

        An organization qualifies if it has an overdue task nobody has been
        told about yet, or an open task held by an offboarded employee.

        The one deliberate exception to row-level security in this module,
        and the scan's only way to find which organizations to look at: with
        no tenant context set, RLS returns nothing. It calls the ``SECURITY
        DEFINER`` function ``organizations_needing_task_scan()`` (see its
        migration), which reveals only organization ids.

        Returns:
            The ids of the organizations to scan.
        """
        result = await self._db.execute(text("SELECT organization_id FROM organizations_needing_task_scan()"))
        return [row.organization_id for row in result]

    async def list_open_tasks_of_inactive_employees(self) -> list[Task]:
        """List the open tasks assigned to employees who have been offboarded.

        Runs inside one organization's RLS context. Completed and cancelled
        tasks are left out: their history stays on the person's name.
        """
        stmt = (
            select(Task)
            .join(Employee, Employee.id == Task.assigned_to_employee_id)
            .where(
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_STATUSES),
                Employee.status == EmployeeStatus.INACTIVE.value,
            )
            .order_by(Task.created_at, Task.id)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def unassign_task(self, task_id: uuid.UUID, expected_assignee_id: uuid.UUID) -> Task | None:
        """Atomically take a task off its assignee, but only if they are still the assignee.

        Same safe pattern as reassign: if somebody reassigned the task in the
        meantime, nothing changes. The task stays open; its assignee becomes
        empty, so it falls back to the department queue.

        Args:
            task_id: Id of the task.
            expected_assignee_id: The assignee the caller saw.

        Returns:
            The updated ``Task``, or ``None`` if nothing matched.
        """
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_STATUSES),
                Task.assigned_to_employee_id == expected_assignee_id,
            )
            .values(assigned_to_employee_id=None)
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def claim_unannounced_overdue_tasks(self, now: datetime) -> list[Task]:
        """Mark every overdue task not yet announced as announced, and return them.

        One UPDATE finds the tasks AND marks them, so two workers running at
        the same time can't both announce the same task: the second one's
        UPDATE no longer matches it. Runs inside the current organization's
        RLS context, so it only sees that organization's tasks. The caller
        commits after sending the notifications, so if sending fails the
        marks are rolled back too and the next run tries again.

        Args:
            now: The moment "overdue" is judged against, also stored as the
                time of announcement.

        Returns:
            The tasks that were just marked.
        """
        stmt = (
            update(Task)
            .where(
                overdue_clause(now),
                Task.deleted_at.is_(None),
                Task.overdue_notified_at.is_(None),
            )
            .values(overdue_notified_at=now)
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return list(result.scalars().all())

    async def cancel_task(self, task_id: uuid.UUID, reason: str) -> Task | None:
        """Atomically cancel a task, but only if it is still open or in progress.

        Same shape as :meth:`complete_task`: the "still open?" check is part
        of the UPDATE, so a cancel racing a completion (or another cancel)
        has exactly one winner.

        Args:
            task_id: Id of the task to cancel.
            reason: Why it is being cancelled.

        Returns:
            The cancelled ``Task``, or ``None`` if nothing changed (it was
            already completed or cancelled, or doesn't exist).
        """
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_STATUSES),
            )
            .values(status=TaskStatus.CANCELLED.value, cancel_reason=reason)
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def reassign_task(
        self,
        task_id: uuid.UUID,
        expected_assignee_id: uuid.UUID | None,
        new_assignee_id: uuid.UUID,
        due_at: datetime,
    ) -> Task | None:
        """Atomically hand a task to someone else with a fresh deadline.

        The UPDATE only matches if the task is still open or in progress
        *and still assigned to whoever the caller saw*. Two simultaneous
        reassignments therefore can't both succeed, and the "old assignee"
        the service writes to the audit log is guaranteed to be true. The
        status goes back to ``open``: the new assignee hasn't started it.

        Args:
            task_id: Id of the task.
            expected_assignee_id: The assignee the caller read (``None`` for
                an unassigned task).
            new_assignee_id: The new assignee.
            due_at: The new deadline.

        Returns:
            The updated ``Task``, or ``None`` if nothing matched (it closed,
            or somebody else reassigned it first).
        """
        # "Still assigned to who the caller saw". An unassigned task has no
        # assignee (NULL), and NULL can't be compared with ==, so it needs .is_(None).
        if expected_assignee_id is None:
            still_assigned_as_seen = Task.assigned_to_employee_id.is_(None)
        else:
            still_assigned_as_seen = Task.assigned_to_employee_id == expected_assignee_id

        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_STATUSES),
                still_assigned_as_seen,
            )
            .values(
                assigned_to_employee_id=new_assignee_id,
                due_at=due_at,
                status=TaskStatus.OPEN.value,
                overdue_notified_at=None,  # the new deadline gets its own alert
                # A clean slate for the new assignee: blocked time approved for the
                # previous person belonged to their deadline, not this one.
                blocked_since=None,
                approved_blocked_seconds=0,
            )
            .returning(Task)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()
