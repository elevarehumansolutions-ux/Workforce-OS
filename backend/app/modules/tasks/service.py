"""Business logic for the Task module.

Wraps :class:`TaskRepository` with the rules the database alone can't
express: who may create, see, edit and complete a task, where a task for
another department lands, and the audit trail. Services flush via the
repository but never commit; the router commits after a successful call.

The decisions behind these rules are in 08_DECISIONS.md 2026-10-07.
"""

import decimal
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DepartmentNotFoundException,
    EmployeeNotFoundException,
    KPINotFoundException,
    NotClockedInException,
    PermissionDeniedException,
    TaskAlreadyBlockedException,
    TaskBlockAlreadyReviewedException,
    TaskBlockNotFoundException,
    TaskChangedException,
    TaskNotBlockedException,
    TaskNotFoundException,
    TaskNotOpenException,
    ValidationException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.attendance.repository import AttendanceRepository
from app.modules.audit_and_notification.service import AuditService, NotificationService
from app.modules.kpis.enums import KPITrackingMode
from app.modules.kpis.repository import KPIRepository
from app.modules.kpis.service import KPIService
from app.modules.organization.enums import EmployeeStatus
from app.modules.organization.models import Employee
from app.modules.organization.repository import (
    DepartmentRepository,
    EmployeeRepository,
    PositionRepository,
)
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.repository import OrganizationRepository
from app.modules.tenancy_identity.service import MembershipService

from .enums import OPEN_STATUSES, BlockCategory, ReviewStatus, TaskStatus
from .models import Task, TaskBlock
from .periods import current_fiscal_quarter
from .repository import TaskRepository, TaskScope
from .schemas import KPITaskProgressResponse, TaskBlockResponse, TaskBlockReviewItem

# Roles that can see every task in the organization.
_ORG_WIDE_ROLES = [MembershipRole.HR_ADMINISTRATOR.value, MembershipRole.BUSINESS_EXECUTIVE.value]
_CLOCK_IN_MESSAGE = "Clock in to see and work on your tasks."


class _CallerContext:
    """Who is calling, as far as task rules care.

    Attributes:
        membership: The caller's membership (role, user, organization).
        employee: The caller's employee record, or ``None`` (a founder or HR
            administrator often has none).
        own_department_id: The department the caller works in, via their
            position, or ``None`` without an employee record.
        headed_department_ids: A list of departments the caller is the named head of.
        clocked_in: Whether the caller is clocked in right now. Tasks are
            "never shown before clock-in" (01_REQUIREMENTS.md), so an
            employee who isn't clocked in does not get the "assigned to me"
            part of their view; see :meth:`scope`.
        is_hr: Whether the caller is an HR administrator.
    """

    def __init__(
        self,
        membership: Membership,
        employee: Employee | None,
        own_department_id: uuid.UUID | None,
        headed_department_ids: list[uuid.UUID],
        clocked_in: bool,
    ):
        """Store who the caller is."""
        self.membership = membership
        self.employee = employee
        self.own_department_id = own_department_id
        self.headed_department_ids = headed_department_ids
        self.clocked_in = clocked_in
        self.is_hr = membership.role == MembershipRole.HR_ADMINISTRATOR.value

    def is_assignee(self, task: Task) -> bool:
        """Whether the caller is the employee the task is assigned to."""
        return self.employee is not None and task.assigned_to_employee_id == self.employee.id

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
        """The set of tasks this caller may see.

        The clock-in gate lives here: a caller who isn't clocked in is given
        no employee id, so the "assigned to me" clause matches nothing. Only
        that clause is gated. What they see as a creator, a department head,
        a manager, HR or an executive is unaffected, so Tunde can still look
        after Dispatch before he clocks in.
        """
        # Departments whose tasks I may see: the ones I head, plus my own
        # department if I have the manager role.
        departments = list(self.headed_department_ids)
        is_manager = self.membership.role == MembershipRole.MANAGER.value
        if is_manager and self.own_department_id and self.own_department_id not in departments:
            departments.append(self.own_department_id)

        # The clock-in gate: not clocked in means no employee id, so the
        # "assigned to me" check can never match.
        employee_id = None
        if self.employee is not None and self.clocked_in:
            employee_id = self.employee.id

        return TaskScope(
            sees_all=self.membership.role in _ORG_WIDE_ROLES,
            user_id=self.membership.user_id,
            employee_id=employee_id,
            department_ids=departments,
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
        self._attendance_repo = AttendanceRepository(db)
        self._organization_repo = OrganizationRepository(db)
        self._audit = AuditService(db)
        self._notifications = NotificationService(db)

    async def _context(self, caller: Membership) -> _CallerContext:
        """Work out the caller's employee record, department, headed departments and clock-in."""
        employee = await self._employee_repo.get_employee_by_user_id(caller.user_id)
        own_department_id = None
        headed_department_ids = []
        clocked_in = False

        # Someone with no employee record (a founder or HR administrator, say)
        # has no department, heads nothing and can't be clocked in.
        if employee is not None:
            # "Clocked in" means an open attendance record (no clock-out yet).
            open_record = await self._attendance_repo.get_open_record(employee.id)
            clocked_in = open_record is not None

            position = await self._position_repo.get_position_by_id(employee.position_id)
            if position is not None:
                own_department_id = position.department_id

            headed_departments = await self._department_repo.list_departments_headed_by(employee.id)
            for department in headed_departments:
                headed_department_ids.append(department.id)

        return _CallerContext(caller, employee, own_department_id, headed_department_ids, clocked_in)

    async def _load_visible(self, task_id: uuid.UUID, ctx: _CallerContext) -> Task:
        """Fetch a task the caller may see; anything else is simply 'not found'.

        A task that exists but is outside the caller's view returns the same
        404 as one that doesn't exist, so its existence isn't revealed. The
        one exception is the clock-in gate: if the caller is the task's
        assignee and would see it but for not being clocked in, they already
        know it exists, so they get an explicit 409 that tells the app what to
        ask them to do.

        Raises:
            TaskNotFoundException: If it doesn't exist or the caller can't see it.
            NotClockedInException: If the caller is the assignee, sees it only
                as such, and isn't clocked in.
        """
        task = await self._repo.get_task_by_id(task_id)
        if task is None:
            raise TaskNotFoundException()
        if ctx.scope().allows(task):
            return task
        if ctx.is_assignee(task):
            # Assignees are always in scope when clocked in, so this is the gate.
            raise NotClockedInException(message=_CLOCK_IN_MESSAGE)
        raise TaskNotFoundException()

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
        overdue: bool | None = None,
        now: datetime | None = None,
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
            overdue: True for only overdue tasks, False for only tasks that
                are not overdue, None for both.
            now: The moment "overdue" is judged against. The router passes
                the same moment it uses for each row's flag; defaults to the
                current time.

        Returns:
            A paginated response of ``Task`` rows.

        Raises:
            NotClockedInException: If the caller asks for their own tasks
                (``assigned_to_employee_id`` is their own id) and isn't
                clocked in. Without this the screen would get an empty list
                and could not tell "nothing today" from "clock in first".
        """
        ctx = await self._context(caller)
        if (
            ctx.employee is not None
            and assigned_to_employee_id == ctx.employee.id
            and not ctx.clocked_in
        ):
            raise NotClockedInException(message=_CLOCK_IN_MESSAGE)

        if now is None:
            now = datetime.now(UTC)
        return await self._repo.list_tasks(
            ctx.scope(),
            department_id,
            assigned_to_employee_id,
            status,
            kpi_id,
            page,
            limit,
            overdue=overdue,
            now=now,
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
        if task.status not in OPEN_STATUSES:
            raise TaskNotOpenException()
        if data.get("kpi_id") is not None:
            await self._validate_kpi(data["kpi_id"])

        old_data =jsonable_encoder({field: getattr(task, field) for field in data})
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
        now = datetime.now(UTC)
        await self._end_open_block(task.id, now)  # before the update, so the response is fresh
        completed = await self._repo.complete_task(task.id, now)
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
        await self._end_open_block(task.id, datetime.now(UTC))  # before the update, so the response is fresh
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
        if task.status not in OPEN_STATUSES:
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
        await self._end_open_block(task.id, datetime.now(UTC))  # before the update, so the response is fresh
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

    async def block_task(
        self, caller: Membership, task_id: uuid.UUID, category: BlockCategory, reason: str
    ) -> TaskBlock:
        """Mark a task blocked: it can't move forward because of something outside the assignee's hands.

        Only the person the task is assigned to can do this. While blocked the
        task is never overdue. The block then waits for a reviewer to approve
        or reject it. ``blocked_at`` is always now, never backdated, so a block
        recorded after the deadline is plainly a late one.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
            PermissionDeniedException: If the caller is not the assignee.
            TaskNotOpenException: If the task is completed or cancelled.
            TaskAlreadyBlockedException: If it is blocked already.
            TaskChangedException: If somebody changed it at the same moment.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        if not ctx.is_assignee(task):
            raise PermissionDeniedException(
                "Only the person the task is assigned to can mark it blocked"
            )
        if task.status not in OPEN_STATUSES:
            raise TaskNotOpenException()
        if task.blocked_since is not None:
            raise TaskAlreadyBlockedException()

        now = datetime.now(UTC)
        if await self._repo.mark_task_blocked(task.id, now) is None:
            # It was open and unblocked when we read it, so somebody changed it in between.
            raise TaskChangedException()
        block = await self._repo.create_block(
            {
                "organization_id": task.organization_id,
                "task_id": task.id,
                "blocked_by_user_id": caller.user_id,
                "category": category.value,
                "reason": reason,
                "blocked_at": now,
            }
        )
        await self._audit.log_action(
            organization_id=task.organization_id,
            actor_user_id=caller.user_id,
            action="block",
            entity_type="task",
            entity_id=task.id,
            changes={
                "old": {"blocked": False},
                "new": jsonable_encoder(
                    {"blocked": True, "block_id": block.id, "category": category.value, "reason": reason}
                ),
            },
        )
        await self._notify_reviewers(task, block)
        return block

    async def unblock_task(self, caller: Membership, task_id: uuid.UUID) -> TaskBlock:
        """End a task's current block, because whatever it was waiting for has arrived.

        Allowed to the assignee, the department head and HR (a head may need to
        free a task whose assignee is away). The blocked period is closed. If a
        reviewer has already approved it, that time is credited to the task now;
        otherwise it is credited when the reviewer approves.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
            PermissionDeniedException: If the caller may see but not unblock it.
            TaskNotBlockedException: If the task is not blocked.
            TaskChangedException: If somebody changed it at the same moment.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        if not (ctx.is_assignee(task) or ctx.is_hr or ctx.heads(task.department_id)):
            raise PermissionDeniedException(
                "Only the assignee, the department head or HR can unblock a task"
            )
        block = await self._repo.get_open_block(task.id)
        if block is None:
            raise TaskNotBlockedException()

        closed = await self._close_block(task.id, block, datetime.now(UTC))
        await self._audit.log_action(
            organization_id=task.organization_id,
            actor_user_id=caller.user_id,
            action="unblock",
            entity_type="task",
            entity_id=task.id,
            changes={
                "old": jsonable_encoder({"blocked": True, "block_id": closed.id}),
                "new": jsonable_encoder({"blocked": False, "unblocked_at": closed.unblocked_at}),
            },
        )
        return closed

    async def list_blocks_for_review(
        self,
        caller: Membership,
        review_status: ReviewStatus | None = ReviewStatus.PENDING,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the blocks the caller is allowed to review, newest first.

        Pending ones by default (the reviewer's to-do list). Each row carries
        the task's title, department and deadline, because a reviewer such as
        the blocker's reporting manager may not be allowed to open the task.

        Args:
            caller: The acting membership.
            review_status: Only blocks in this state; ``None`` for all.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response of ``TaskBlockReviewItem`` rows.
        """
        ctx = await self._context(caller)
        manager_employee_id = ctx.employee.id if ctx.employee is not None else None
        result = await self._repo.list_blocks_for_review(
            reviewer_user_id=caller.user_id,
            sees_all=ctx.is_hr,
            department_ids=ctx.headed_department_ids,
            manager_employee_id=manager_employee_id,
            review_status=review_status,
            page=page,
            limit=limit,
        )
        tasks = await self._repo.get_tasks_by_ids([block.task_id for block in result.data])
        items = []
        for block in result.data:
            task = tasks[block.task_id]
            fields = TaskBlockResponse.model_validate(block).model_dump()
            items.append(
                TaskBlockReviewItem(
                    **fields,
                    task_title=task.title,
                    task_department_id=task.department_id,
                    task_due_at=task.due_at,
                )
            )
        result.data = items
        return result

    async def approve_block(self, caller: Membership, block_id: uuid.UUID) -> TaskBlock:
        """Approve a block: its blocked time is not held against the assignee.

        Allowed to HR, the head of the task's department and the blocker's
        reporting manager, never to the blocker. If the block has already
        ended, its length is added to the task's approved blocked time now
        (pushing the deadline later); if the task is still blocked, that
        happens when it is unblocked.

        Raises:
            TaskBlockNotFoundException: If it doesn't exist or the caller may not review it.
            TaskBlockAlreadyReviewedException: If it was already approved or rejected.
        """
        return await self._review_block(caller, block_id, ReviewStatus.APPROVED)

    async def reject_block(self, caller: Membership, block_id: uuid.UUID) -> TaskBlock:
        """Reject a block: the task is judged as if it had never been blocked.

        Same rules and errors as :meth:`approve_block`.
        """
        return await self._review_block(caller, block_id, ReviewStatus.REJECTED)

    async def _review_block(
        self, caller: Membership, block_id: uuid.UUID, decision: ReviewStatus
    ) -> TaskBlock:
        """Record a reviewer's decision on a block (shared by approve and reject)."""
        ctx = await self._context(caller)
        block = await self._repo.get_block_by_id(block_id)
        task = None
        if block is not None:
            task = await self._repo.get_task_by_id(block.task_id)
        # Not found and not-allowed look the same, so a block's existence isn't revealed.
        if block is None or task is None or not await self._can_review(ctx, block, task):
            raise TaskBlockNotFoundException()
        if block.review_status != ReviewStatus.PENDING.value:
            raise TaskBlockAlreadyReviewedException()

        reviewed = await self._repo.review_block(block.id, decision, caller.user_id, datetime.now(UTC))
        if reviewed is None:
            raise TaskBlockAlreadyReviewedException()  # someone decided at the same moment

        if decision == ReviewStatus.APPROVED and reviewed.unblocked_at is not None:
            seconds = int((reviewed.unblocked_at - reviewed.blocked_at).total_seconds())
            await self._repo.add_approved_seconds(task.id, seconds)

        await self._audit.log_action(
            organization_id=task.organization_id,
            actor_user_id=caller.user_id,
            action=f"{decision.value}_block",
            entity_type="task_block",
            entity_id=reviewed.id,
            changes={
                "old": {"review_status": ReviewStatus.PENDING.value},
                "new": {"review_status": decision.value, "task_id": str(task.id)},
            },
        )
        await self._notifications.notify(
            organization_id=task.organization_id,
            recipient_user_ids=[reviewed.blocked_by_user_id],
            category=NotificationCategory.TASK,
            title=f"Block {decision.value}: {task.title}",
            body=(
                "Your blocked time was approved and won't count against you."
                if decision == ReviewStatus.APPROVED
                else "Your block was rejected, so the task is judged as if it was not blocked."
            ),
            link_type="task",
            link_id=task.id,
        )
        return reviewed

    async def _can_review(self, ctx: _CallerContext, block: TaskBlock, task: Task) -> bool:
        """Whether the caller may approve or reject ``block``.

        HR, the head of the task's department, or the blocker's own reporting
        manager. Nobody reviews their own block, whoever they are. The database
        form of this rule is ``TaskRepository.list_blocks_for_review``.
        """
        if block.blocked_by_user_id == ctx.membership.user_id:
            return False
        if ctx.is_hr or ctx.heads(task.department_id):
            return True
        blocker = await self._employee_repo.get_employee_by_user_id(block.blocked_by_user_id)
        if blocker is None or blocker.manager_id is None or ctx.employee is None:
            return False
        return blocker.manager_id == ctx.employee.id

    async def _review_recipients(self, task: Task, block: TaskBlock) -> list[uuid.UUID]:
        """Work out who to tell that a block needs review.

        The blocker's reporting manager if they have one (and a login);
        otherwise the department head; otherwise the HR administrators. The
        first group that has anyone wins, and the blocker is never in it.
        """
        # 1. The blocker's own reporting manager.
        blocker = await self._employee_repo.get_employee_by_user_id(block.blocked_by_user_id)
        if blocker is not None and blocker.manager_id is not None:
            boss = await self._employee_repo.get_employee_by_id(blocker.manager_id)
            if boss is not None and boss.status != EmployeeStatus.INACTIVE.value and boss.user_id is not None:
                if boss.user_id != block.blocked_by_user_id:
                    return [boss.user_id]

        # 2. The head of the task's department.
        department = await self._department_repo.get_department_by_id(task.department_id)
        if department is not None and department.head_employee_id is not None:
            head = await self._employee_repo.get_employee_by_id(department.head_employee_id)
            if head is not None and head.user_id is not None:
                if head.user_id != block.blocked_by_user_id:
                    return [head.user_id]

        # 3. The HR administrators.
        hr_user_ids = await self._membership_service.list_active_user_ids_by_role(
            task.organization_id, MembershipRole.HR_ADMINISTRATOR.value
        )
        return [user_id for user_id in hr_user_ids if user_id != block.blocked_by_user_id]

    async def _notify_reviewers(self, task: Task, block: TaskBlock) -> None:
        """Tell whoever should review a new block that it is waiting for them."""
        recipients = await self._review_recipients(task, block)
        if not recipients:
            return
        category = block.category.replace("_", " ")
        await self._notifications.notify(
            organization_id=task.organization_id,
            recipient_user_ids=recipients,
            category=NotificationCategory.TASK,
            title=f"Task blocked: {task.title}",
            body=f"Reason ({category}): {block.reason}. It needs your review.",
            link_type="task_block",
            link_id=block.id,
        )

    async def _end_open_block(self, task_id: uuid.UUID, now: datetime) -> None:
        """End the task's open block, if it has one.

        Called when a task is completed, cancelled or reassigned: a block
        shouldn't outlive the situation it describes. The block's review
        status is left alone, so a reviewer can still judge it for the record.
        """
        block = await self._repo.get_open_block(task_id)
        if block is not None:
            await self._close_block(task_id, block, now)

    async def _close_block(self, task_id: uuid.UUID, block: TaskBlock, now: datetime) -> TaskBlock:
        """End ``block`` at ``now`` and update the task to match.

        Used when someone unblocks, and also when a blocked task is cancelled
        or reassigned (the block ends with it). If the block is already
        approved, its length is added to the task's approved blocked time.

        Raises:
            TaskChangedException: If the block was closed by somebody else first.
        """
        closed = await self._repo.close_block(block.id, now)
        if closed is None:
            raise TaskChangedException()
        approved_seconds = 0
        if closed.review_status == ReviewStatus.APPROVED.value:
            approved_seconds = int((closed.unblocked_at - closed.blocked_at).total_seconds())
        await self._repo.clear_blocked_state(task_id, approved_seconds)
        return closed

    async def list_task_blocks(self, caller: Membership, task_id: uuid.UUID) -> list[TaskBlock]:
        """List every block a task has had, newest first, for a caller who can see the task.

        Raises:
            TaskNotFoundException: If it doesn't exist or is outside the caller's view.
        """
        ctx = await self._context(caller)
        task = await self._load_visible(task_id, ctx)
        return await self._repo.list_blocks_for_task(task.id)

    async def get_kpi_task_progress(
        self, caller: Membership, kpi_id: uuid.UUID, now: datetime | None = None
    ) -> KPITaskProgressResponse:
        """Live progress of a task-count KPI: completed linked tasks this fiscal quarter.

        Example: "Close 20 deals", seven linked tasks completed this quarter,
        gives 7 completed and 35%. Nothing is stored; the count is made now.
        The percentage uses the KPI module's own rule, so it matches a typed-in
        value exactly (no target means no percentage; inverse KPIs are honoured).

        Any member of the organization may read it, as with the KPI itself.

        Args:
            caller: The acting membership.
            kpi_id: The KPI.
            now: The current moment; tests pass a fixed one.

        Returns:
            The count for the current fiscal quarter, with the percentage.

        Raises:
            KPINotFoundException: If the KPI doesn't exist in the caller's organization.
            ValidationException: If the KPI is tracked by typed-in values, not by task count.
        """
        kpi = await self._kpi_repo.get_kpi_by_id(kpi_id)
        if kpi is None:
            raise KPINotFoundException()
        if kpi.tracking_mode != KPITrackingMode.TASK_COUNT.value:
            raise ValidationException(
                message="This KPI is tracked by typed-in values, not by counting tasks"
            )

        organization = await self._organization_repo.get_organization_by_id(caller.organization_id)
        if now is None:
            now = datetime.now(UTC)
        period_start, period_end = current_fiscal_quarter(
            organization.fiscal_year_start_month, organization.timezone, now
        )
        completed = await self._repo.count_completed_tasks_for_kpi(kpi.id, period_start, period_end)
        score_percentage = KPIService.calculate_score_percentage(
            decimal.Decimal(completed), kpi.target_value, kpi.is_inverse
        )
        return KPITaskProgressResponse(
            kpi_id=kpi.id,
            period_start=period_start.date(),
            period_end=(period_end - timedelta(days=1)).date(),  # the last day, inclusive
            completed_tasks=completed,
            target_value=kpi.target_value,
            unit=kpi.unit,
            score_percentage=score_percentage,
        )

    async def release_orphaned_tasks(self, organization_id: uuid.UUID) -> int:
        """Hand over the open tasks of employees who have been offboarded.

        A departure is a handover (08_DECISIONS.md 2026-10-09). For each open
        task still assigned to an inactive employee: its open block (if any)
        is ended, and it becomes unassigned, which puts it back in the
        department queue. Then the department's head (or the HR
        administrators, if there is no head) is told, in one message per
        department and person who left, so they can reassign each task with a
        new deadline. Completed and cancelled tasks are never touched.

        Called by the task scan once per organization, with that
        organization's RLS context already set. Safe to run repeatedly: once
        a task is unassigned it no longer matches.

        Args:
            organization_id: The organization being scanned.

        Returns:
            How many tasks were handed over.
        """
        orphaned_tasks = await self._repo.list_open_tasks_of_inactive_employees()
        now = datetime.now(UTC)
        titles_by_department_and_person: dict[tuple[uuid.UUID, uuid.UUID], list[str]] = {}

        for task in orphaned_tasks:
            former_assignee_id = task.assigned_to_employee_id  # read before the update changes it
            await self._end_open_block(task.id, now)
            released = await self._repo.unassign_task(task.id, former_assignee_id)
            if released is None:
                continue  # somebody reassigned it in the meantime
            await self._audit.log_action(
                organization_id=organization_id,
                actor_user_id=None,  # a system action, not a person
                action="unassign",
                entity_type="task",
                entity_id=task.id,
                changes={
                    "old": {"assigned_to_employee_id": str(former_assignee_id)},
                    "new": {"assigned_to_employee_id": None, "reason": "the assignee was offboarded"},
                },
            )
            group = (task.department_id, former_assignee_id)
            titles_by_department_and_person.setdefault(group, []).append(task.title)

        for (department_id, former_assignee_id), titles in titles_by_department_and_person.items():
            await self._tell_about_released_tasks(organization_id, department_id, former_assignee_id, titles)
        return sum(len(titles) for titles in titles_by_department_and_person.values())

    async def _tell_about_released_tasks(
        self,
        organization_id: uuid.UUID,
        department_id: uuid.UUID,
        former_assignee_id: uuid.UUID,
        titles: list[str],
    ) -> None:
        """Tell a department's head (or HR) that a leaver's tasks now need a new owner."""
        recipients = await self._head_or_hr_user_ids(department_id, organization_id)
        if not recipients:
            return
        former = await self._employee_repo.get_employee_by_id(former_assignee_id)
        name = f"{former.first_name} {former.last_name}" if former is not None else "An employee"
        shown = ", ".join(f'"{title}"' for title in titles[:5])
        more = f" and {len(titles) - 5} more" if len(titles) > 5 else ""
        await self._notifications.notify(
            organization_id=organization_id,
            recipient_user_ids=recipients,
            category=NotificationCategory.TASK,
            title=f"{name} left: {len(titles)} task(s) need a new owner",
            body=f"These tasks have no owner now: {shown}{more}. Assign each one to someone, with a new deadline.",
            link_type="department",
            link_id=department_id,
        )

    async def announce_overdue_tasks(self, organization_id: uuid.UUID, now: datetime) -> int:
        """Tell the right people about every overdue task not announced yet.

        Called by the overdue scan (``tasks/tasks.py``) once per organization,
        with that organization's RLS context already set. Each overdue task is
        announced once: the claim marks it, so the next scan skips it, until
        its deadline changes. The router commits after this returns.

        Args:
            organization_id: The organization being scanned.
            now: The moment "overdue" is judged against.

        Returns:
            How many tasks were announced.
        """
        tasks = await self._repo.claim_unannounced_overdue_tasks(now)
        for task in tasks:
            recipient_ids = await self._overdue_recipients(task)
            if not recipient_ids:
                continue  # nobody to tell (no HR administrator with a login either)
            await self._notifications.notify(
                organization_id=organization_id,
                recipient_user_ids=recipient_ids,
                category=NotificationCategory.TASK,
                title=f"Task overdue: {task.title}",
                body=f'"{task.title}" was due {task.due_at:%d %b %Y, %H:%M} UTC and is not done yet.',
                link_type="task",
                link_id=task.id,
            )
            await self._prompt_assignee_to_explain(task)
        return len(tasks)

    async def _prompt_assignee_to_explain(self, task: Task) -> None:
        """Invite the assignee to record a block, if the task is overdue and has never had one.

        The "why is this late?" prompt (01_REQUIREMENTS.md 6a): if something
        outside their control held the task up, they can say so and a reviewer
        will judge it. Skipped when the task is unassigned, the assignee has
        left or has no login, or they have already recorded a block.
        """
        if task.assigned_to_employee_id is None:
            return
        if await self._repo.list_blocks_for_task(task.id):
            return  # they have already explained
        assignee = await self._employee_repo.get_employee_by_id(task.assigned_to_employee_id)
        if assignee is None or assignee.status == EmployeeStatus.INACTIVE.value or assignee.user_id is None:
            return
        await self._notifications.notify(
            organization_id=task.organization_id,
            recipient_user_ids=[assignee.user_id],
            category=NotificationCategory.TASK,
            title=f"Was something holding up: {task.title}?",
            body=(
                "This task is overdue. If something outside your control held it up, "
                "mark it blocked and say why, so a reviewer can take it into account."
            ),
            link_type="task",
            link_id=task.id,
        )

    async def _overdue_recipients(self, task: Task) -> list[uuid.UUID]:
        """Work out which users to tell that ``task`` is overdue.

        The assignee (if there is one, still active, and has a login), plus
        the department's head. If the department has no head (or the head has
        no login), the HR administrators are told instead, so an overdue task
        is never left with nobody accountable. Nobody appears twice.
        """
        user_ids = []

        if task.assigned_to_employee_id is not None:
            assignee = await self._employee_repo.get_employee_by_id(task.assigned_to_employee_id)
            if (
                assignee is not None
                and assignee.status != EmployeeStatus.INACTIVE.value
                and assignee.user_id is not None
            ):
                user_ids.append(assignee.user_id)

        for user_id in await self._head_or_hr_user_ids(task.department_id, task.organization_id):
            if user_id not in user_ids:
                user_ids.append(user_id)

        return user_ids

    async def _head_or_hr_user_ids(
        self, department_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """The people accountable for a department's tasks: its head, else the HR administrators.

        If the department has no head (or the head has no login), the HR
        administrators are returned instead, so there is always someone.
        """
        head = None
        department = await self._department_repo.get_department_by_id(department_id)
        if department is not None and department.head_employee_id is not None:
            head = await self._employee_repo.get_employee_by_id(department.head_employee_id)

        if head is not None and head.user_id is not None:
            return [head.user_id]
        return await self._membership_service.list_active_user_ids_by_role(
            organization_id, MembershipRole.HR_ADMINISTRATOR.value
        )

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
