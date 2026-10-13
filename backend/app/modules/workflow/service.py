"""Business logic for the Workflow module.

Services flush via the repository but never commit; the router commits after
a successful call, same convention as the other modules. See
08_DECISIONS.md 2026-10-12 for the rules implemented here.
"""

import uuid
from datetime import UTC, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DepartmentNotFoundException,
    EmployeeNotFoundException,
    PermissionDeniedException,
    ResourceInUseException,
    ValidationException,
    WorkflowInstanceNotFoundException,
    WorkflowStepNotFoundException,
    WorkflowTemplateAlreadyArchivedException,
    WorkflowTemplateArchivedException,
    WorkflowTemplateNotArchivedException,
    WorkflowTemplateNotFoundException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.service import AuditService, NotificationService
from app.modules.organization.enums import EmployeeStatus
from app.modules.organization.repository import DepartmentRepository, EmployeeRepository
from app.modules.tasks.service import TaskService
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.repository import OrganizationRepository, UserRepository

from .deadlines import add_business_hours
from .enums import InstanceStatus
from .models import WorkflowInstance, WorkflowStep, WorkflowTemplate
from .repository import InstanceRepository, InstanceScope, StepRepository, TemplateRepository


class TemplateService:
    """Business logic for building and reading workflow templates."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = TemplateRepository(db)
        self._department_repo = DepartmentRepository(db)
        self._audit = AuditService(db)

    async def create_template(self, caller: Membership, data: dict) -> WorkflowTemplate:
        """Create a template owned by one of the organization's departments.

        The router has already checked the caller is HR or a manager.

        Args:
            caller: The caller's membership (gives the organization and user).
            data: ``name`` and ``department_id`` from the request.

        Returns:
            The newly created template.

        Raises:
            DepartmentNotFoundException: If the department isn't in the caller's org.
        """
        department = await self._department_repo.get_department_by_id(data["department_id"])
        if department is None:
            raise DepartmentNotFoundException()

        template = await self._repo.create_template(
            {
                **data,
                "organization_id": caller.organization_id,
                "created_by_user_id": caller.user_id,
            }
        )
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="create",
            entity_type="workflow_template",
            entity_id=template.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return template

    async def update_template(
        self, caller: Membership, template_id: uuid.UUID, data: dict
    ) -> WorkflowTemplate:
        """Change a template's name and/or owning department.

        Allowed while cases are running on it: neither field affects them (the
        steps, not the template's name or owner, decide what happens next).
        The router has already checked the caller is HR or a manager.

        Args:
            caller: The caller's membership (gives the organization and user).
            template_id: Id of the template to change.
            data: Only the fields to change.

        Returns:
            The updated template.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            DepartmentNotFoundException: If the new department isn't in the caller's org.
        """
        template = await self.get_template(template_id)
        if "department_id" in data:
            department = await self._department_repo.get_department_by_id(data["department_id"])
            if department is None:
                raise DepartmentNotFoundException()

        # Read the old values before the update: it changes this same object.
        old_values = {field: getattr(template, field) for field in data}
        template = await self._repo.update_template(template, data)
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="update",
            entity_type="workflow_template",
            entity_id=template.id,
            changes={"old": jsonable_encoder(old_values), "new": jsonable_encoder(data)},
        )
        return template

    async def delete_template(
        self, caller: Membership, template_id: uuid.UUID
    ) -> WorkflowTemplate:
        """Soft-delete a template that no case is running on.

        Finished and cancelled cases keep their history; the template's steps
        are left as they are (old tasks still point at them). To stop people
        using a template that has running cases, archive it instead.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            ResourceInUseException: If any case is still in progress on it.
        """
        template = await self.get_template(template_id)
        running = await self._repo.count_running_instances(template.id)
        if running > 0:
            raise ResourceInUseException(
                message=(
                    f"Cannot delete template: {running} case(s) are still running on it. "
                    "Archive it instead, or wait until they finish."
                )
            )

        old_values = {"deleted_at": jsonable_encoder(template.deleted_at)}
        deleted_at = datetime.now(UTC)
        template = await self._repo.update_template(template, {"deleted_at": deleted_at})
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="delete",
            entity_type="workflow_template",
            entity_id=template.id,
            changes={"old": old_values, "new": {"deleted_at": jsonable_encoder(deleted_at)}},
        )
        return template

    async def archive_template(
        self, caller: Membership, template_id: uuid.UUID
    ) -> WorkflowTemplate:
        """Retire a template: it can't start new cases, running ones carry on.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            WorkflowTemplateAlreadyArchivedException: If it is already archived.
        """
        template = await self.get_template(template_id)
        if template.archived_at is not None:
            raise WorkflowTemplateAlreadyArchivedException()
        return await self._set_archived(caller, template, datetime.now(UTC), "archive")

    async def unarchive_template(
        self, caller: Membership, template_id: uuid.UUID
    ) -> WorkflowTemplate:
        """Bring an archived template back into use.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            WorkflowTemplateNotArchivedException: If it is not archived.
        """
        template = await self.get_template(template_id)
        if template.archived_at is None:
            raise WorkflowTemplateNotArchivedException()
        return await self._set_archived(caller, template, None, "unarchive")

    async def _set_archived(
        self, caller: Membership, template: WorkflowTemplate, archived_at, action: str
    ) -> WorkflowTemplate:
        """Set or clear ``archived_at`` and record who did it, with old and new."""
        old_value = template.archived_at  # read before the update changes the object
        template = await self._repo.update_template(template, {"archived_at": archived_at})
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action=action,
            entity_type="workflow_template",
            entity_id=template.id,
            changes={
                "old": {"archived_at": jsonable_encoder(old_value)},
                "new": {"archived_at": jsonable_encoder(archived_at)},
            },
        )
        return template

    async def get_template(self, template_id: uuid.UUID) -> WorkflowTemplate:
        """Fetch one template. Open to any member.

        Args:
            template_id: Id of the template to fetch.

        Returns:
            The matching template.

        Raises:
            WorkflowTemplateNotFoundException: If it doesn't exist, was deleted,
                or belongs to another organization.
        """
        template = await self._repo.get_template_by_id(template_id)
        if template is None:
            raise WorkflowTemplateNotFoundException()
        return template

    async def list_templates(
        self,
        caller: Membership,
        include_archived: bool = False,
        department_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the organization's templates. Open to any member.

        Args:
            caller: The caller's membership (gives the organization).
            include_archived: Also return retired templates.
            department_id: Only templates this department owns.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching templates.
        """
        return await self._repo.list_templates(
            caller.organization_id, include_archived, department_id, page, limit
        )


class StepService:
    """Business logic for building the steps of a template."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._template_repo = TemplateRepository(db)
        self._step_repo = StepRepository(db)
        self._department_repo = DepartmentRepository(db)
        self._employee_repo = EmployeeRepository(db)
        self._task_service = TaskService(db)
        self._audit = AuditService(db)

    async def add_step(
        self, caller: Membership, template_id: uuid.UUID, data: dict
    ) -> WorkflowStep:
        """Add a step to a template, at the given position or at the end.

        Allowed on an archived template and while cases are running on it:
        a running case reads "what comes next" from the template when a task
        finishes, so a new step is simply passed through. The router has
        already checked the caller is HR or a manager.

        Args:
            caller: The caller's membership (gives the organization and user).
            template_id: Template to add the step to.
            data: The step's fields; ``step_order`` empty means "at the end".

        Returns:
            The newly created step.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            DepartmentNotFoundException: If the department isn't in the caller's org.
            EmployeeNotFoundException: If the default assignee isn't an employee here.
            ValidationException: If the assignee was offboarded, or the position
                is not between 1 and one past the last step.
        """
        # Lock the template: two people adding at once must take turns, or
        # both would read the same step count and pick the same position.
        template = await self._template_repo.get_template_by_id(template_id, lock=True)
        if template is None:
            raise WorkflowTemplateNotFoundException()
        await self._check_department(data["department_id"])
        if data.get("default_assignee_employee_id") is not None:
            await self._check_assignee(data["default_assignee_employee_id"])

        step_count = await self._step_repo.count_steps(template.id)
        position = data.get("step_order") or step_count + 1
        if position > step_count + 1:
            raise ValidationException(
                message=f"The position must be between 1 and {step_count + 1} for this template"
            )
        await self._step_repo.make_room_at(template.id, position)

        step = await self._step_repo.create_step(
            {
                **data,
                "step_order": position,
                "organization_id": caller.organization_id,
                "workflow_template_id": template.id,
            }
        )
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="create",
            entity_type="workflow_step",
            entity_id=step.id,
            changes={
                "old": None,
                "new": jsonable_encoder({**data, "step_order": position, "workflow_template_id": template.id}),
            },
        )
        return step

    async def update_step(
        self, caller: Membership, step_id: uuid.UUID, data: dict
    ) -> WorkflowStep:
        """Change a step's name, department, default assignee or turnaround.

        Tasks already created from the step keep their deadlines; the change
        applies to tasks created from now on (08_DECISIONS.md 2026-10-12).
        Sending ``None`` for the assignee or turnaround clears it. The router
        has already checked the caller is HR or a manager.

        Args:
            caller: The caller's membership (gives the organization and user).
            step_id: Id of the step to change.
            data: Only the fields to change.

        Returns:
            The updated step.

        Raises:
            WorkflowStepNotFoundException: If the step isn't in the caller's org.
            DepartmentNotFoundException: If the new department isn't in the caller's org.
            EmployeeNotFoundException: If the new default assignee isn't an employee here.
            ValidationException: If the new assignee was offboarded.
        """
        step = await self._step_repo.get_step_by_id(step_id)
        if step is None:
            raise WorkflowStepNotFoundException()
        if "department_id" in data:
            await self._check_department(data["department_id"])
        if data.get("default_assignee_employee_id") is not None:
            await self._check_assignee(data["default_assignee_employee_id"])

        # Read the old values before the update: it changes this same object.
        old_values = {field: getattr(step, field) for field in data}
        step = await self._step_repo.update_step(step, data)
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="update",
            entity_type="workflow_step",
            entity_id=step.id,
            changes={"old": jsonable_encoder(old_values), "new": jsonable_encoder(data)},
        )
        return step

    async def reorder_steps(
        self, caller: Membership, template_id: uuid.UUID, ordered_ids: list[uuid.UUID]
    ) -> list[WorkflowStep]:
        """Put a template's steps in a new order.

        Refused while any case is running on the template: "what comes next"
        is read from the template when a task finishes, so moving a step
        behind a case that is already past it would silently skip that step.
        The list must contain every step of the template exactly once.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            ResourceInUseException: If a case is in progress on the template.
            ValidationException: If the ids are not exactly the template's steps.
        """
        # Lock the template so two reorders (or a reorder and an add) take turns.
        template = await self._template_repo.get_template_by_id(template_id, lock=True)
        if template is None:
            raise WorkflowTemplateNotFoundException()

        running = await self._template_repo.count_running_instances(template.id)
        if running > 0:
            raise ResourceInUseException(
                message=(
                    f"Cannot reorder steps: {running} case(s) are still running on this "
                    "template. Wait until they finish, or build a new template."
                )
            )

        steps = await self._step_repo.list_steps(template.id)
        if sorted(ordered_ids) != sorted(step.id for step in steps):
            raise ValidationException(
                message=(
                    "The list must contain every step of this template exactly once "
                    f"({len(steps)} step(s))"
                )
            )

        old_order = [step.id for step in steps]
        if ordered_ids == old_order:
            return steps  # nothing to change, so nothing to record
        reordered = await self._step_repo.reorder_steps(steps, ordered_ids)
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="reorder",
            entity_type="workflow_template",
            entity_id=template.id,
            changes={
                "old": {"step_ids": jsonable_encoder(old_order)},
                "new": {"step_ids": jsonable_encoder(ordered_ids)},
            },
        )
        return reordered

    async def delete_step(self, caller: Membership, step_id: uuid.UUID) -> WorkflowStep:
        """Soft-delete a step that no open task sits on, and close the gap.

        The later steps move up one place, so steps 1, 2, 3, 4 with step 2
        deleted become 1, 2, 3. Allowed while cases are running, as long as
        none of them has an open task on this step.

        Raises:
            WorkflowStepNotFoundException: If the step isn't in the caller's org.
            ResourceInUseException: If a task created from it is still open.
        """
        step = await self._step_repo.get_step_by_id(step_id)
        if step is None:
            raise WorkflowStepNotFoundException()
        # Lock the template so renumbering takes turns with other changes to
        # its steps, then look the step up again: someone else may have
        # deleted it while we waited for the lock.
        await self._template_repo.get_template_by_id(step.workflow_template_id, lock=True)
        step = await self._step_repo.get_step_by_id(step_id)
        if step is None:
            raise WorkflowStepNotFoundException()

        open_tasks = await self._task_service.count_open_tasks_for_step(step.id)
        if open_tasks > 0:
            raise ResourceInUseException(
                message=(
                    f"Cannot delete step: {open_tasks} task(s) are still open on it. "
                    "Finish or cancel them first."
                )
            )

        # Read before the update: it changes this same object.
        old_values = {"step_order": step.step_order, "deleted_at": jsonable_encoder(step.deleted_at)}
        deleted_at = datetime.now(UTC)
        step = await self._step_repo.update_step(step, {"deleted_at": deleted_at})
        await self._step_repo.close_gap_after(step.workflow_template_id, step.step_order)
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="delete",
            entity_type="workflow_step",
            entity_id=step.id,
            changes={"old": old_values, "new": {"deleted_at": jsonable_encoder(deleted_at)}},
        )
        return step

    async def list_steps(self, template_id: uuid.UUID) -> list[WorkflowStep]:
        """List a template's steps in order. Open to any member.

        Works for archived templates too.

        Raises:
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        """
        template = await self._template_repo.get_template_by_id(template_id)
        if template is None:
            raise WorkflowTemplateNotFoundException()
        return await self._step_repo.list_steps(template.id)

    async def _check_department(self, department_id: uuid.UUID) -> None:
        """Make sure the department exists in the caller's organization."""
        if await self._department_repo.get_department_by_id(department_id) is None:
            raise DepartmentNotFoundException()

    async def _check_assignee(self, employee_id: uuid.UUID) -> None:
        """Make sure the default assignee is an active employee of the organization."""
        employee = await self._employee_repo.get_employee_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundException()
        if employee.status == EmployeeStatus.INACTIVE.value:
            raise ValidationException(message="An offboarded employee can't be a step's default assignee")


# Roles that see every case in the organization.
_SEES_EVERY_CASE_ROLES = (
    MembershipRole.HR_ADMINISTRATOR.value,
    MembershipRole.BUSINESS_EXECUTIVE.value,
)


class InstanceService:
    """Business logic for running cases: starting them and, later, moving them along."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._template_repo = TemplateRepository(db)
        self._step_repo = StepRepository(db)
        self._instance_repo = InstanceRepository(db)
        self._department_repo = DepartmentRepository(db)
        self._employee_repo = EmployeeRepository(db)
        self._organization_repo = OrganizationRepository(db)
        self._user_repo = UserRepository(db)
        self._task_service = TaskService(db)
        self._audit = AuditService(db)
        self._notifications = NotificationService(db)

    async def start_instance(
        self, caller: Membership, template_id: uuid.UUID, subject: str
    ) -> WorkflowInstance:
        """Start a case from a template and create the first step's task.

        Who may start: any active employee, and HR administrators (who may not
        have an employee record yet). The template is locked while this runs,
        so an archive or delete at the same moment can't slip past the checks.

        Args:
            caller: The caller's membership (gives the organization and user).
            template_id: The process to run.
            subject: What the case is about, such as a client's name.

        Returns:
            The new case, in progress, with its first task already created.

        Raises:
            PermissionDeniedException: If the caller is neither HR nor an active employee.
            WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
            WorkflowTemplateArchivedException: If the template has been archived.
            ValidationException: If the template has no steps.
        """
        await self._check_may_start(caller)

        template = await self._template_repo.get_template_by_id(template_id, lock=True)
        if template is None:
            raise WorkflowTemplateNotFoundException()
        if template.archived_at is not None:
            raise WorkflowTemplateArchivedException()
        steps = await self._step_repo.list_steps(template.id)
        if not steps:
            raise ValidationException(
                message="This template has no steps yet. Add at least one step before starting a case"
            )

        instance = await self._instance_repo.create_instance(
            {
                "organization_id": caller.organization_id,
                "workflow_template_id": template.id,
                "subject": subject,
                "started_by_user_id": caller.user_id,
            }
        )
        await self._create_task_for_step(instance, template, steps[0], len(steps), datetime.now(UTC))
        await self._audit.log_action(
            organization_id=caller.organization_id,
            actor_user_id=caller.user_id,
            action="start",
            entity_type="workflow_instance",
            entity_id=instance.id,
            changes={
                "old": None,
                "new": jsonable_encoder(
                    {"workflow_template_id": template.id, "subject": subject, "status": instance.status}
                ),
            },
        )
        return instance

    async def list_instances(
        self,
        caller: Membership,
        status: InstanceStatus | None = None,
        template_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the cases the caller may see, newest first.

        HR administrators and business executives see every case; everyone
        else sees the cases they started, have a task in, or head a department
        that has a step in.
        """
        scope = await self._scope_for(caller)
        return await self._instance_repo.list_instances(scope, status, template_id, page, limit)

    async def get_instance(self, caller: Membership, instance_id: uuid.UUID) -> dict:
        """Fetch one case the caller may see, with its steps and its tasks so far.

        Returns:
            The case, the template's current steps (in order) and the tasks the
            case has created (oldest first), as ``{"instance", "steps", "tasks"}``.

        Raises:
            WorkflowInstanceNotFoundException: If it doesn't exist or is outside
                the caller's view.
        """
        scope = await self._scope_for(caller)
        instance = await self._instance_repo.get_instance_by_id(instance_id, scope)
        if instance is None:
            raise WorkflowInstanceNotFoundException()
        steps = await self._step_repo.list_steps(instance.workflow_template_id)
        tasks = await self._task_service.list_tasks_for_workflow_instance(instance.id)
        return {"instance": instance, "steps": steps, "tasks": tasks}

    async def _scope_for(self, caller: Membership) -> InstanceScope:
        """Work out which cases ``caller`` may see."""
        employee = await self._employee_repo.get_employee_by_user_id(caller.user_id)
        cases_with_my_tasks = []
        headed_department_ids = []
        if employee is not None:
            cases_with_my_tasks = await self._task_service.workflow_instance_ids_for_assignee(employee.id)
            headed = await self._department_repo.list_departments_headed_by(employee.id)
            headed_department_ids = [department.id for department in headed]
        return InstanceScope(
            sees_all=caller.role in _SEES_EVERY_CASE_ROLES,
            user_id=caller.user_id,
            instance_ids_with_my_tasks=cases_with_my_tasks,
            headed_department_ids=headed_department_ids,
        )

    async def move_on_after_task(
        self,
        *,
        instance_id: uuid.UUID,
        finished_step_id: uuid.UUID | None,
        finished_task_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        skipped_reason: str | None = None,
    ) -> None:
        """A task of a case has ended: create the next step's task, or finish the case.

        Called by the listeners when a task is completed, or cancelled by
        hand (a "skip", when ``skipped_reason`` is given). "What comes next" is
        read from the template as it is now, so steps added or removed since
        the case started are respected. The next deadline counts from this
        moment, in business hours.

        Does nothing if the case is no longer in progress: a case that was
        cancelled at the same moment must not grow a new task.

        Args:
            instance_id: The case the task belongs to.
            finished_step_id: The step the task was made from.
            finished_task_id: The task that just ended.
            actor_user_id: Who completed or cancelled it.
            skipped_reason: The cancel reason when the task was cancelled by
                hand; ``None`` when it was completed.

        Raises:
            ValidationException: If the finished task's step no longer exists
                in the template (it should not happen: a step with an open
                task cannot be deleted).
        """
        # Lock the case, then its template: another change to the same case or
        # its steps waits until this one is done.
        instance = await self._instance_repo.get_instance_for_update(instance_id)
        if instance is None or instance.status != InstanceStatus.IN_PROGRESS.value:
            return
        template = await self._template_repo.get_template_by_id(instance.workflow_template_id, lock=True)
        steps = await self._step_repo.list_steps(instance.workflow_template_id)

        finished_step = next((step for step in steps if step.id == finished_step_id), None)
        if finished_step is None:
            raise ValidationException(
                message="This task's workflow step no longer exists. Ask an HR administrator to check the workflow"
            )
        steps_after = [step for step in steps if step.step_order > finished_step.step_order]
        next_step = steps_after[0] if steps_after else None

        now = datetime.now(UTC)
        if next_step is not None:
            await self._create_task_for_step(instance, template, next_step, len(steps), now)
        else:
            await self._instance_repo.update_instance(
                instance, {"status": InstanceStatus.COMPLETED.value, "completed_at": now}
            )
            await self._audit.log_action(
                organization_id=instance.organization_id,
                actor_user_id=actor_user_id,
                action="complete",
                entity_type="workflow_instance",
                entity_id=instance.id,
                changes={
                    "old": {"status": InstanceStatus.IN_PROGRESS.value, "completed_at": None},
                    "new": {"status": InstanceStatus.COMPLETED.value, "completed_at": jsonable_encoder(now)},
                },
            )

        if skipped_reason is not None:
            await self._record_and_announce_skip(
                instance, finished_step, finished_task_id, next_step, actor_user_id, skipped_reason
            )

    async def _record_and_announce_skip(
        self,
        instance: WorkflowInstance,
        skipped_step: WorkflowStep,
        skipped_task_id: uuid.UUID,
        next_step: WorkflowStep | None,
        actor_user_id: uuid.UUID | None,
        reason: str,
    ) -> None:
        """Write the skip to the audit log and tell the case's starter (not themselves)."""
        await self._audit.log_action(
            organization_id=instance.organization_id,
            actor_user_id=actor_user_id,
            action="skip_step",
            entity_type="workflow_instance",
            entity_id=instance.id,
            changes={
                "old": None,
                "new": jsonable_encoder(
                    {
                        "step_id": skipped_step.id,
                        "step_name": skipped_step.name,
                        "task_id": skipped_task_id,
                        "reason": reason,
                        "moved_on_to_step_id": next_step.id if next_step is not None else None,
                    }
                ),
            },
        )

        starter_id = instance.started_by_user_id
        if starter_id is None or starter_id == actor_user_id:
            return  # nobody to tell, or they skipped it themselves
        actor_name = "Someone"
        if actor_user_id is not None:
            actor = await self._user_repo.get_user_by_id(actor_user_id)
            if actor is not None:
                actor_name = actor.full_name
        if next_step is not None:
            outcome = f"The case moved on to \"{next_step.name}\"."
        else:
            outcome = "That was the last step, so the case is now complete."
        await self._notifications.notify(
            organization_id=instance.organization_id,
            recipient_user_ids=[starter_id],
            category=NotificationCategory.TASK,
            title=f"A step was skipped on {instance.subject}",
            body=f"\"{skipped_step.name}\" was skipped by {actor_name}: {reason}. {outcome}",
            link_type="workflow_instance",
            link_id=instance.id,
        )

    async def _check_may_start(self, caller: Membership) -> None:
        """Only HR administrators and active employees may start a case."""
        if caller.role == MembershipRole.HR_ADMINISTRATOR.value:
            return
        employee = await self._employee_repo.get_employee_by_user_id(caller.user_id)
        if employee is None or employee.status == EmployeeStatus.INACTIVE.value:
            raise PermissionDeniedException("Only employees can start a workflow")

    async def _create_task_for_step(
        self,
        instance: WorkflowInstance,
        template: WorkflowTemplate,
        step: WorkflowStep,
        step_count: int,
        now: datetime,
    ) -> None:
        """Ask the Task module for the task that represents ``step``.

        The deadline is the business-hours deadline from ``now`` (none when
        the step has no turnaround). The Task module deals with a missing or
        departed default assignee.
        """
        due_at = None
        if step.default_turnaround_hours is not None:
            organization = await self._organization_repo.get_organization_by_id(instance.organization_id)
            due_at = add_business_hours(now, step.default_turnaround_hours, organization.timezone)

        await self._task_service.create_workflow_task(
            organization_id=instance.organization_id,
            department_id=step.department_id,
            # A step name and a subject can each be 200 characters; keep the title readable.
            title=f"{step.name}: {instance.subject}"[:255],
            due_at=due_at,
            workflow_instance_id=instance.id,
            workflow_step_id=step.id,
            assigned_to_employee_id=step.default_assignee_employee_id,
            description=f"Step {step.step_order} of {step_count} in \"{template.name}\" for {instance.subject}.",
        )
