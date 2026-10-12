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
    ResourceInUseException,
    ValidationException,
    WorkflowStepNotFoundException,
    WorkflowTemplateAlreadyArchivedException,
    WorkflowTemplateNotArchivedException,
    WorkflowTemplateNotFoundException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.service import AuditService
from app.modules.organization.enums import EmployeeStatus
from app.modules.organization.repository import DepartmentRepository, EmployeeRepository
from app.modules.tasks.service import TaskService
from app.modules.tenancy_identity.models import Membership

from .models import WorkflowStep, WorkflowTemplate
from .repository import StepRepository, TemplateRepository


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
