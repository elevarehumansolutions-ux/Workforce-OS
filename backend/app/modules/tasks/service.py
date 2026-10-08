"""Business logic for the Task module.

Wraps :class:`TaskRepository` with the rules the database alone can't
express: who may create, see, edit and complete a task, where a task for
another department lands, and the audit trail. Services flush via the
repository but never commit; the router commits after a successful call.

The decisions behind these rules are in 08_DECISIONS.md 2026-10-07.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DepartmentNotFoundException,
    EmployeeNotFoundException,
    KPINotFoundException,
    PermissionDeniedException,
    TaskChangedException,
    TaskNotFoundException,
    TaskNotOpenException,
    ValidationException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.service import AuditService, NotificationService
from app.modules.kpis.repository import KPIRepository
from app.modules.organization.enums import EmployeeStatus
from app.modules.organization.models import Employee
from app.modules.organization.repository import (
    DepartmentRepository,
    EmployeeRepository,
    PositionRepository,
)
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.service import MembershipService

from .enums import TaskStatus
from .models import Task
from .repository import TaskRepository, TaskScope

_ORG_WIDE_ROLES = {MembershipRole.HR_ADMINISTRATOR.value, MembershipRole.BUSINESS_EXECUTIVE.value}
_OPEN_STATUSES = {TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value}


@dataclass(frozen=True)
class _CallerContext:
    """Who is calling, as far as task rules care.

    Attributes:
        membership: The caller's membership (role, user, organization).
        employee: The caller's employee record, or ``None`` (a founder or HR
            administrator often has none).
        own_department_id: The department the caller works in, via their
            position, or ``None`` without an employee record.
        headed_department_ids: Departments the caller is the named head of.
    """

    membership: Membership
    employee: Employee | None
    own_department_id: uuid.UUID | None
    headed_department_ids: frozenset[uuid.UUID]

    @property
    def is_hr(self) -> bool:
        """Whether the caller is an HR administrator."""
        return self.membership.role == MembershipRole.HR_ADMINISTRATOR.value

    def heads(self, department_id: uuid.UUID) -> bool:
        """Whether the caller is the named head of ``department_id``."""
        return department_id in self.headed_department_ids

    def can_manage(self, task: Task) -> bool:
        """Whether the caller may edit ``task``: HR, its department's head, or its creator."""
        return (
            self.is_hr
            or self.heads(task.department_id)
            or task.created_by_user_id == self.membership.user_id
        )

    def can_reassign(self, task: Task) -> bool:
        """Whether the caller may hand ``task`` to someone else.

        HR, the department's head, or the task's creator *if they work in that
        department*. A creator from another department can't choose the
        individual, here any more than when creating (the head delegates).
        """
        return (
            self.is_hr
            or self.heads(task.department_id)
            or (
                task.created_by_user_id == self.membership.user_id
                and self.own_department_id == task.department_id
            )
        )

    def scope(self) -> TaskScope:
        """The set of tasks this caller may see."""
        departments = set(self.headed_department_ids)
        if self.membership.role == MembershipRole.MANAGER.value and self.own_department_id:
            departments.add(self.own_department_id)
        return TaskScope(
            sees_all=self.membership.role in _ORG_WIDE_ROLES,
            user_id=self.membership.user_id,
            employee_id=self.employee.id if self.employee else None,
            department_ids=frozenset(departments),
        )


class TaskService:
    """Business logic for creating, reading, updating and completing tasks."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = TaskRepository(db)
        self._employee_repo = EmployeeRepository(db)
        self._department_repo = DepartmentRepository(db)
        self._position_repo = PositionRepository(db)
        self._kpi_repo = KPIRepository(db)
        self._membership_service = MembershipService(db)
        self._audit = AuditService(db)
        self._notifications = NotificationService(db)

    async def _context(self, caller: Membership) -> _CallerContext:
        """Work out the caller's employee record, department and headed departments."""
        employee = await self._employee_repo.get_employee_by_user_id(caller.user_id)
        own_department_id = None
        headed: frozenset[uuid.UUID] = frozenset()
        if employee is not None:
            position = await self._position_repo.get_position_by_id(employee.position_id)
            if position is not None:
                own_department_id = position.department_id
            headed = frozenset(
                d.id for d in await self._department_repo.list_departments_headed_by(employee.id)
            )
        return _CallerContext(caller, employee, own_department_id, headed)

    async def _load_visible(self, task_id: uuid.UUID, ctx: _CallerContext) -> Task:
        """Fetch a task the caller may see; anything else is simply 'not found'.

        A task that exists but is outside the caller's view returns the same
        404 as one that doesn't exist, so its existence isn't revealed.

        Raises:
            TaskNotFoundException: If it doesn't exist or the caller can't see it.
        """
        task = await self._repo.get_task_by_id(task_id)
        if task is None or not ctx.scope().allows(task):
            raise TaskNotFoundException()
        return task

    async def _validate_assignee(self, employee_id: uuid.UUID) -> Employee:
        """Check an employee can be given a task: in this org and still active.

        Raises:
            EmployeeNotFoundException: If not an employee of the caller's org.
            ValidationException: If the employee has been offboarded.
        """
        employee = await self._employee_repo.get_employee_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundException()
        if employee.status == EmployeeStatus.INACTIVE.value:
            raise ValidationException(message="An offboarded employee can't be assigned a task")
        return employee

    async def _validate_kpi(self, kpi_id: uuid.UUID) -> None:
        """Check a KPI exists in this organization.

        Raises:
            KPINotFoundException: If no non-deleted KPI with that id is visible.
        """
        if await self._kpi_repo.get_kpi_by_id(kpi_id) is None:
            raise KPINotFoundException()

    async def create_task(self, caller: Membership, data: dict) -> Task:
        """Create a task, working out who it goes to.

        Who may create: an HR administrator, a member with the ``manager``
        role, or the named head of the task's department. Everyone else
        gets a 403.

        Where it goes: ``department_id`` is the department that does the
        work. A creator from *another* department (not HR, not that
        department's head) cannot choose the individual: the task lands with
        the work department's head, who delegates. If that department has no
        head, the task stays unassigned and the HR administrators are told.
        Everyone else may name an assignee, or leave it for the department
        queue.

        Args:
            caller: The acting membership.
            data: Field values for the new task (``department_id``, ``title``,
                and optionally ``description``, ``due_at``, ``kpi_id``,
                ``assigned_to_employee_id``).

        Returns:
            The newly created ``Task``.

        Raises:
            DepartmentNotFoundException: If the department isn't in the caller's org.
            PermissionDeniedException: If the caller may not create tasks.
            ValidationException: If an outsider names an assignee, or the
                assignee has been offboarded.
            EmployeeNotFoundException: If the assignee isn't an employee here.
            KPINotFoundException: If ``kpi_id`` isn't a KPI of the caller's org.
        """
        ctx = await self._context(caller)
        department = await self._department_repo.get_department_by_id(data["department_id"])
        if department is None:
            raise DepartmentNotFoundException()

        is_head = ctx.heads(department.id)
        if not (ctx.is_hr or caller.role == MembershipRole.MANAGER.value or is_head):
            raise PermissionDeniedException(
                "Only HR administrators, managers and department heads can create tasks"
            )
        if data.get("kpi_id") is not None:
            await self._validate_kpi(data["kpi_id"])

        assignee_id = data.get("assigned_to_employee_id")
        outsider = not ctx.is_hr and not is_head and ctx.own_department_id != department.id
        if outsider and assignee_id is not None:
            raise ValidationException(
                message=(
                    f"A task for another department goes to {department.name}'s head, who "
                    "assigns it. Leave the assignee empty."
                )
            )
        if assignee_id is not None:
            await self._validate_assignee(assignee_id)

        head_missing = False
        if assignee_id is None and outsider:
            assignee_id = department.head_employee_id
            head_missing = assignee_id is None

        task = await self._repo.create_task(
            {
                **data,
                "assigned_to_employee_id": assignee_id,
                "organization_id": caller.organization_id,
                "created_by_user_id": caller.user_id,
            }
        )
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="create",
            entity_type="task",
            entity_id=task.id,
            changes={
                "old": None,
                "new": jsonable_encoder(
                    {
                        "department_id": task.department_id,
                        "title": task.title,
                        "due_at": task.due_at,
                        "kpi_id": task.kpi_id,
                        "assigned_to_employee_id": task.assigned_to_employee_id,
                    }
                ),
            },
        )
        await self._notify_about_new_task(task, department.name, caller, head_missing)
        return task

    async def _notify_about_new_task(
        self, task: Task, department_name: str, caller: Membership, head_missing: bool
    ) -> None:
        """Tell the assignee, or the HR administrators if nobody could receive it.

        Nobody is notified about a task they created for themselves.
        """
        if task.assigned_to_employee_id is not None:
            assignee = await self._employee_repo.get_employee_by_id(task.assigned_to_employee_id)
            if assignee is not None and assignee.user_id not in (None, caller.user_id):
                await self._notifications.notify(
                    organization_id=task.organization_id,
                    recipient_user_ids=[assignee.user_id],
                    category=NotificationCategory.TASK,
                    title=f"New task: {task.title}",
                    body=f"A task for {department_name} has been assigned to you.",
                    link_type="task",
                    link_id=task.id,
                )
        elif head_missing:
            recipients = await self._membership_service.list_active_user_ids_by_role(
                task.organization_id, MembershipRole.HR_ADMINISTRATOR.value
            )
            if recipients:
                await self._notifications.notify(
                    organization_id=task.organization_id,
                    recipient_user_ids=recipients,
                    category=NotificationCategory.TASK,
                    title=f"A task for {department_name} has no one to receive it",
                    body=(
                        f"\"{task.title}\" was created for {department_name}, which has no "
                        "department head. Assign the task, or name a head."
                    ),
                    link_type="task",
                    link_id=task.id,
                )

    async def get_task(self, caller: Membership, task_id: uuid.UUID) -> Task:
        """Fetch one task the caller is allowed to see.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
        """
        return await self._load_visible(task_id, await self._context(caller))

    async def list_tasks(
        self,
        caller: Membership,
        department_id: uuid.UUID | None = None,
        assigned_to_employee_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        kpi_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the tasks the caller may see, with optional filters.

        Args:
            caller: The acting membership.
            department_id: Only tasks for this department.
            assigned_to_employee_id: Only tasks assigned to this employee.
            status: Only tasks in this status.
            kpi_id: Only tasks linked to this KPI.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response of ``Task`` rows.
        """
        ctx = await self._context(caller)
        return await self._repo.list_tasks(
            ctx.scope(), department_id, assigned_to_employee_id, status, kpi_id, page, limit
        )

    async def update_task(self, caller: Membership, task_id: uuid.UUID, data: dict) -> Task:
        """Edit a task's title, description, deadline or KPI link.

        Allowed to HR, the department's head and the task's creator; not to
        the assignee (they can't move their own deadline). An authorized
        person may deliberately change ``due_at``; the change is audit-logged
        with old and new values. A completed or cancelled task can't be edited.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
            PermissionDeniedException: If the caller may see but not edit it.
            TaskNotOpenException: If it is already completed or cancelled.
            KPINotFoundException: If ``kpi_id`` isn't a KPI of the caller's org.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        if not ctx.can_manage(task):
            raise PermissionDeniedException(
                "Only HR, the department head or the task's creator can edit a task"
            )
        if task.status not in _OPEN_STATUSES:
            raise TaskNotOpenException()
        if data.get("kpi_id") is not None:
            await self._validate_kpi(data["kpi_id"])

        old_data = jsonable_encoder({field: getattr(task, field) for field in data})
        task = await self._repo.update_task(task, data)
        await self._audit.log_action(
            organization_id=task.organization_id,
            actor_user_id=caller.user_id,
            action="update",
            entity_type="task",
            entity_id=task.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return task

    async def complete_task(self, caller: Membership, task_id: uuid.UUID) -> Task:
        """Mark a task completed.

        Allowed to the assignee, the department's head and HR. The close is
        one atomic conditional UPDATE, so two people completing it at once
        can't both succeed and the first completion time stands.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
            PermissionDeniedException: If the caller may see but not complete it.
            TaskNotOpenException: If it is already completed or cancelled.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        is_assignee = ctx.employee is not None and task.assigned_to_employee_id == ctx.employee.id
        if not (is_assignee or ctx.is_hr or ctx.heads(task.department_id)):
            raise PermissionDeniedException(
                "Only the assignee, the department head or HR can complete a task"
            )

        # Read before the UPDATE: it refreshes this same object in place.
        old_status = task.status
        completed = await self._repo.complete_task(task.id, datetime.now(UTC))
        if completed is None:
            raise TaskNotOpenException()
        await self._audit.log_action(
            organization_id=completed.organization_id,
            actor_user_id=caller.user_id,
            action="complete",
            entity_type="task",
            entity_id=completed.id,
            changes={
                "old": {"status": old_status},
                "new": {
                    "status": completed.status,
                    "completed_at": jsonable_encoder(completed.completed_at),
                },
            },
        )
        return completed

    async def cancel_task(self, caller: Membership, task_id: uuid.UUID, reason: str) -> Task:
        """Cancel a task that is no longer needed.

        Allowed to HR, the department's head and the task's creator, **not**
        the assignee (they complete or ask; they don't withdraw work). Final:
        a cancelled task counts neither as completed nor as late. A completed
        task can't be cancelled. The reason is stored on the task and the
        assignee, if someone else, is told.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
            PermissionDeniedException: If the caller may see but not cancel it.
            TaskNotOpenException: If it is already completed or cancelled.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        if not ctx.can_manage(task):
            raise PermissionDeniedException(
                "Only HR, the department head or the task's creator can cancel a task"
            )

        # Read before the UPDATE: it refreshes this same object in place.
        old_status = task.status
        cancelled = await self._repo.cancel_task(task.id, reason)
        if cancelled is None:
            raise TaskNotOpenException()
        await self._audit.log_action(
            organization_id=cancelled.organization_id,
            actor_user_id=caller.user_id,
            action="cancel",
            entity_type="task",
            entity_id=cancelled.id,
            changes={
                "old": {"status": old_status},
                "new": {"status": cancelled.status, "cancel_reason": reason},
            },
        )
        await self._notify_employee(
            cancelled,
            cancelled.assigned_to_employee_id,
            caller,
            title=f"Task cancelled: {cancelled.title}",
            body=f"This task was cancelled. Reason: {reason}",
        )
        return cancelled

    async def reassign_task(
        self,
        caller: Membership,
        task_id: uuid.UUID,
        assigned_to_employee_id: uuid.UUID,
        due_at: datetime,
    ) -> Task:
        """Give a task to someone (else), with a new deadline.

        Also the way to assign a task that landed unassigned. Every
        reassignment needs a new future ``due_at`` so the new assignee gets a
        fair clock rather than inheriting the previous one's lateness
        (08_DECISIONS.md 2026-10-07). The status goes back to ``open``. Allowed
        to HR, the department's head, and the creator when they work in the
        task's department. The new assignee is told, and so is the previous one.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
            PermissionDeniedException: If the caller may see but not reassign it.
            TaskNotOpenException: If it is already completed or cancelled.
            ValidationException: If ``due_at`` isn't in the future, the assignee
                is already the assignee, or has been offboarded.
            EmployeeNotFoundException: If the new assignee isn't an employee here.
            TaskChangedException: If somebody else reassigned it first.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        if not ctx.can_reassign(task):
            raise PermissionDeniedException(
                "Only HR, the department head or the task's creator in that department "
                "can reassign a task"
            )
        if task.status not in _OPEN_STATUSES:
            raise TaskNotOpenException()
        if due_at <= datetime.now(UTC):
            raise ValidationException(message="A reassigned task needs a new deadline in the future")
        if task.assigned_to_employee_id == assigned_to_employee_id:
            raise ValidationException(
                message="That person already has this task. To move the deadline, edit the task"
            )
        await self._validate_assignee(assigned_to_employee_id)

        previous_assignee_id = task.assigned_to_employee_id
        old_due_at = task.due_at
        old_status = task.status
        updated = await self._repo.reassign_task(
            task.id, previous_assignee_id, assigned_to_employee_id, due_at
        )
        if updated is None:
            # Open when we read it, so it was reassigned, completed or cancelled in between.
            raise TaskChangedException()
        await self._audit.log_action(
            organization_id=updated.organization_id,
            actor_user_id=caller.user_id,
            action="reassign",
            entity_type="task",
            entity_id=updated.id,
            changes={
                "old": jsonable_encoder(
                    {
                        "assigned_to_employee_id": previous_assignee_id,
                        "due_at": old_due_at,
                        "status": old_status,
                    }
                ),
                "new": jsonable_encoder(
                    {
                        "assigned_to_employee_id": updated.assigned_to_employee_id,
                        "due_at": updated.due_at,
                        "status": updated.status,
                    }
                ),
            },
        )
        await self._notify_employee(
            updated,
            updated.assigned_to_employee_id,
            caller,
            title=f"New task: {updated.title}",
            body="A task has been assigned to you with a new deadline.",
        )
        await self._notify_employee(
            updated,
            previous_assignee_id,
            caller,
            title=f"Task reassigned: {updated.title}",
            body="This task has been given to someone else and is no longer yours.",
        )
        return updated

    async def _notify_employee(
        self, task: Task, employee_id: uuid.UUID | None, caller: Membership, title: str, body: str
    ) -> None:
        """Send one in-app notification about ``task`` to an employee's login.

        Skipped when there is no employee, the employee has no login yet, or
        the employee is the caller (nobody is notified about their own action).
        """
        if employee_id is None:
            return
        employee = await self._employee_repo.get_employee_by_id(employee_id)
        if employee is None or employee.user_id in (None, caller.user_id):
            return
        await self._notifications.notify(
            organization_id=task.organization_id,
            recipient_user_ids=[employee.user_id],
            category=NotificationCategory.TASK,
            title=title,
            body=body,
            link_type="task",
            link_id=task.id,
        )
