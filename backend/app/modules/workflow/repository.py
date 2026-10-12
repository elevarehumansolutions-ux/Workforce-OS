"""Data-access layer for the Workflow module.

Every repository works inside the caller's RLS-scoped session and only
flushes, never commits: the router commits after a successful call, same
convention as the other modules.
"""

import uuid

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from .enums import InstanceStatus
from .models import WorkflowInstance, WorkflowStep, WorkflowTemplate


class TemplateRepository:
    """Handles persistence for workflow templates."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_template(self, fields: dict) -> WorkflowTemplate:
        """Insert a new template, flush, and refresh it from the database.

        Args:
            fields: Field values for the new ``WorkflowTemplate`` row.

        Returns:
            The newly created and refreshed template.
        """
        template = WorkflowTemplate(**fields)
        self._db.add(template)
        await self._db.flush()
        await self._db.refresh(template)
        return template

    async def get_template_by_id(
        self, template_id: uuid.UUID, lock: bool = False
    ) -> WorkflowTemplate | None:
        """Get a single non-deleted template by its id.

        RLS already restricts this to the caller's current org.

        Args:
            template_id: Id of the template to fetch.
            lock: Lock the row until the transaction ends. Used when the
                template's steps are about to change, so two people changing
                them at once take turns instead of both reading the same
                step count.

        Returns:
            The matching template, or ``None`` if not found.
        """
        stmt = select(WorkflowTemplate).where(
            WorkflowTemplate.id == template_id,
            WorkflowTemplate.deleted_at.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_template(self, template: WorkflowTemplate, fields: dict) -> WorkflowTemplate:
        """Apply a partial update, flush and refresh. The caller commits.

        Args:
            template: The template to change in place.
            fields: Mapping of field names to their new values.

        Returns:
            The updated and refreshed template.
        """
        for field, value in fields.items():
            setattr(template, field, value)
        await self._db.flush()
        await self._db.refresh(template)
        return template

    async def list_templates(
        self,
        organization_id: uuid.UUID,
        include_archived: bool = False,
        department_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted templates for an organization, by name.

        Args:
            organization_id: Organization to list templates for.
            include_archived: If False (the default), retired templates are left out.
            department_id: If given, restrict results to templates this department owns.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching templates.
        """
        stmt = select(WorkflowTemplate).where(
            WorkflowTemplate.organization_id == organization_id,
            WorkflowTemplate.deleted_at.is_(None),
        )
        if not include_archived:
            stmt = stmt.where(WorkflowTemplate.archived_at.is_(None))
        if department_id is not None:
            stmt = stmt.where(WorkflowTemplate.department_id == department_id)
        # The id breaks ties so two templates with the same name never swap
        # places between one page and the next.
        stmt = stmt.order_by(WorkflowTemplate.name.asc(), WorkflowTemplate.id.asc())
        return await paginate(stmt, page, limit, self._db)

    async def count_running_instances(self, template_id: uuid.UUID) -> int:
        """Count the cases still in progress on a template.

        Finished and cancelled cases don't count: they are history and don't
        depend on the template staying editable.

        Args:
            template_id: Template to count running cases for.

        Returns:
            How many instances of it are ``in_progress``.
        """
        stmt = (
            select(func.count())
            .select_from(WorkflowInstance)
            .where(
                WorkflowInstance.workflow_template_id == template_id,
                WorkflowInstance.status == InstanceStatus.IN_PROGRESS.value,
            )
        )
        return (await self._db.scalar(stmt)) or 0


class InstanceScope:
    """Which cases a caller may see.

    HR administrators and business executives see every case. Everyone else
    sees a case if they started it, if they have (or had) a task in it, or if
    they head a department that has a step in its template. Anything else is
    simply not found.
    """

    def __init__(
        self,
        sees_all: bool,
        user_id: uuid.UUID,
        instance_ids_with_my_tasks: list[uuid.UUID],
        headed_department_ids: list[uuid.UUID],
    ):
        """Store who the caller is."""
        self.sees_all = sees_all
        self.user_id = user_id
        self.instance_ids_with_my_tasks = instance_ids_with_my_tasks
        self.headed_department_ids = headed_department_ids


class InstanceRepository:
    """Handles persistence for running cases (workflow instances)."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    @staticmethod
    def _only_visible(stmt, scope: InstanceScope):
        """Narrow a query on cases to the ones ``scope`` may see."""
        if scope.sees_all:
            return stmt
        has_a_step_i_head = exists().where(
            WorkflowStep.workflow_template_id == WorkflowInstance.workflow_template_id,
            WorkflowStep.deleted_at.is_(None),
            WorkflowStep.department_id.in_(scope.headed_department_ids),
        )
        return stmt.where(
            or_(
                WorkflowInstance.started_by_user_id == scope.user_id,
                WorkflowInstance.id.in_(scope.instance_ids_with_my_tasks),
                has_a_step_i_head,
            )
        )

    async def get_instance_by_id(
        self, instance_id: uuid.UUID, scope: InstanceScope
    ) -> WorkflowInstance | None:
        """Get one case by id, if ``scope`` may see it.

        Args:
            instance_id: Id of the case to fetch.
            scope: Which cases the caller may see.

        Returns:
            The case, or ``None`` if it doesn't exist or is outside the scope.
        """
        stmt = self._only_visible(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id), scope
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_instances(
        self,
        scope: InstanceScope,
        status: InstanceStatus | None = None,
        template_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List the cases ``scope`` may see, newest first.

        Args:
            scope: Which cases the caller may see.
            status: Only cases in this status.
            template_id: Only cases of this template.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching cases.
        """
        stmt = self._only_visible(select(WorkflowInstance), scope)
        if status is not None:
            stmt = stmt.where(WorkflowInstance.status == status.value)
        if template_id is not None:
            stmt = stmt.where(WorkflowInstance.workflow_template_id == template_id)
        stmt = stmt.order_by(WorkflowInstance.started_at.desc(), WorkflowInstance.id.desc())
        return await paginate(stmt, page, limit, self._db)

    async def create_instance(self, fields: dict) -> WorkflowInstance:
        """Insert a new case, flush, and refresh it from the database.

        Args:
            fields: Field values for the new ``WorkflowInstance`` row.

        Returns:
            The newly created and refreshed case.
        """
        instance = WorkflowInstance(**fields)
        self._db.add(instance)
        await self._db.flush()
        await self._db.refresh(instance)
        return instance


class StepRepository:
    """Handles persistence for the steps of workflow templates."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def count_steps(self, template_id: uuid.UUID) -> int:
        """Count a template's non-deleted steps.

        Args:
            template_id: Template whose steps to count.

        Returns:
            The number of steps (they are numbered 1 to this count).
        """
        stmt = (
            select(func.count())
            .select_from(WorkflowStep)
            .where(
                WorkflowStep.workflow_template_id == template_id,
                WorkflowStep.deleted_at.is_(None),
            )
        )
        return (await self._db.scalar(stmt)) or 0

    async def get_step_by_id(self, step_id: uuid.UUID) -> WorkflowStep | None:
        """Get a single non-deleted step by its id.

        A step of a deleted template counts as not found: the template is
        gone, so its steps can no longer be reached or changed.

        Args:
            step_id: Id of the step to fetch.

        Returns:
            The matching step, or ``None`` if not found.
        """
        stmt = (
            select(WorkflowStep)
            .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowStep.workflow_template_id)
            .where(
                WorkflowStep.id == step_id,
                WorkflowStep.deleted_at.is_(None),
                WorkflowTemplate.deleted_at.is_(None),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_step(self, step: WorkflowStep, fields: dict) -> WorkflowStep:
        """Apply a partial update, flush and refresh. The caller commits.

        Args:
            step: The step to change in place.
            fields: Mapping of field names to their new values (``None`` clears).

        Returns:
            The updated and refreshed step.
        """
        for field, value in fields.items():
            setattr(step, field, value)
        await self._db.flush()
        await self._db.refresh(step)
        return step

    async def list_steps(self, template_id: uuid.UUID) -> list[WorkflowStep]:
        """List a template's non-deleted steps, first step first.

        Args:
            template_id: Template whose steps to list.

        Returns:
            The steps in position order.
        """
        stmt = (
            select(WorkflowStep)
            .where(
                WorkflowStep.workflow_template_id == template_id,
                WorkflowStep.deleted_at.is_(None),
            )
            .order_by(WorkflowStep.step_order.asc(), WorkflowStep.id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def reorder_steps(
        self, steps: list[WorkflowStep], ordered_ids: list[uuid.UUID]
    ) -> list[WorkflowStep]:
        """Give the steps the positions 1, 2, 3 ... in the order of ``ordered_ids``.

        Args:
            steps: The template's steps (every one of them).
            ordered_ids: The same steps' ids, in the new order.

        Returns:
            The steps in their new order, refreshed from the database.
        """
        steps_by_id = {step.id: step for step in steps}
        reordered = []
        for position, step_id in enumerate(ordered_ids, start=1):
            step = steps_by_id[step_id]
            step.step_order = position
            reordered.append(step)
        await self._db.flush()
        for step in reordered:
            await self._db.refresh(step)
        return reordered

    async def close_gap_after(self, template_id: uuid.UUID, position: int) -> None:
        """Move every step after ``position`` up by one place.

        The mirror of ``make_room_at``: after the step at ``position`` is
        deleted, steps 1, 2, 4, 5 become 1, 2, 3, 4.

        Args:
            template_id: Template whose steps to renumber.
            position: Position of the step that was just deleted.
        """
        stmt = (
            update(WorkflowStep)
            .where(
                WorkflowStep.workflow_template_id == template_id,
                WorkflowStep.deleted_at.is_(None),
                WorkflowStep.step_order > position,
            )
            .values(step_order=WorkflowStep.step_order - 1)
        )
        await self._db.execute(stmt)

    async def make_room_at(self, template_id: uuid.UUID, position: int) -> None:
        """Move every step from ``position`` onward down by one place.

        Example: steps 1, 2, 3 and a new step wanted at position 2 -> the old
        2 and 3 become 3 and 4, leaving 2 free.

        Args:
            template_id: Template whose steps to shift.
            position: First position to move.
        """
        stmt = (
            update(WorkflowStep)
            .where(
                WorkflowStep.workflow_template_id == template_id,
                WorkflowStep.deleted_at.is_(None),
                WorkflowStep.step_order >= position,
            )
            .values(step_order=WorkflowStep.step_order + 1)
        )
        await self._db.execute(stmt)

    async def create_step(self, fields: dict) -> WorkflowStep:
        """Insert a new step, flush, and refresh it from the database.

        Args:
            fields: Field values for the new ``WorkflowStep`` row.

        Returns:
            The newly created and refreshed step.
        """
        step = WorkflowStep(**fields)
        self._db.add(step)
        await self._db.flush()
        await self._db.refresh(step)
        return step
