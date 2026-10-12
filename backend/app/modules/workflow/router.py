"""FastAPI routes for the Workflow module.

Template and step building is for HR administrators and users with the
``manager`` role; reads are open to any member of the organization
(08_DECISIONS.md 2026-10-12).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db, require_org_role
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.models import Membership

from .enums import InstanceStatus
from .schemas import (
    InstanceCreateRequest,
    InstanceDetailResponse,
    InstanceResponse,
    InstanceTaskResponse,
    StepCreateRequest,
    StepOrderRequest,
    StepResponse,
    StepUpdateRequest,
    TemplateCreateRequest,
    TemplateResponse,
    TemplateUpdateRequest,
)
from .service import InstanceService, StepService, TemplateService

router = APIRouter()

_BUILDER_ROLES = (MembershipRole.HR_ADMINISTRATOR.value, MembershipRole.MANAGER.value)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.post("/workflow-templates", status_code=200)
async def create_template(
    data: TemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> TemplateResponse:
    """Create a workflow template in the caller's organization.

    Requires the HR Administrator or Manager role.

    Args:
        data: Template name and owning department.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The newly created template (it has no steps yet).

    Raises:
        DepartmentNotFoundException: If the department isn't in the caller's org.
    """
    service = TemplateService(db)
    template = await service.create_template(caller, data.model_dump())
    # Build the response before committing: commit() clears the RLS context
    # and the template's loaded values (08_DECISIONS.md, the "RLS context is
    # gone after commit()" lesson).
    response = TemplateResponse.model_validate(template)
    await db.commit()
    return response


@router.get("/workflow-templates", status_code=200)
async def list_templates(
    include_archived: bool = Query(default=False),
    department_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List the organization's workflow templates, by name.

    Open to any authenticated member of the organization. Archived templates
    are left out unless ``include_archived`` is true.

    Args:
        include_archived: Also return retired templates.
        department_id: Only templates this department owns.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        A paginated response of templates.
    """
    service = TemplateService(db)
    result = await service.list_templates(caller, include_archived, department_id, page, limit)
    result.data = [TemplateResponse.model_validate(t) for t in result.data]
    return result


@router.get("/workflow-templates/{template_id}", status_code=200)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TemplateResponse:
    """Get one workflow template by id.

    Open to any authenticated member of the organization. Works for archived
    templates too.

    Args:
        template_id: Id of the template to fetch.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        The matching template.

    Raises:
        WorkflowTemplateNotFoundException: If it doesn't exist in the caller's org.
    """
    service = TemplateService(db)
    template = await service.get_template(template_id)
    return TemplateResponse.model_validate(template)


@router.patch("/workflow-templates/{template_id}", status_code=200)
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> TemplateResponse:
    """Change a template's name and/or owning department.

    Requires the HR Administrator or Manager role. Any manager may edit any
    template, not only their own (08_DECISIONS.md 2026-10-12).

    Args:
        template_id: Id of the template to change.
        data: Only the fields to change.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The updated template.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        DepartmentNotFoundException: If the new department isn't in the caller's org.
    """
    service = TemplateService(db)
    # exclude_unset keeps only the fields the client actually sent.
    template = await service.update_template(
        caller, template_id, data.model_dump(exclude_unset=True)
    )
    response = TemplateResponse.model_validate(template)
    await db.commit()
    return response


@router.delete("/workflow-templates/{template_id}", status_code=200)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> TemplateResponse:
    """Soft-delete a template.

    Requires the HR Administrator or Manager role. Blocked while any case is
    still running on the template; archive it instead to stop new cases.

    Args:
        template_id: Id of the template to delete.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The deleted template.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        ResourceInUseException: If any case is still in progress on it.
    """
    service = TemplateService(db)
    template = await service.delete_template(caller, template_id)
    response = TemplateResponse.model_validate(template)
    await db.commit()
    return response


# ---------------------------------------------------------------------------
# Instances (running cases)
# ---------------------------------------------------------------------------

@router.post("/workflow-instances", status_code=200)
async def start_instance(
    data: InstanceCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> InstanceResponse:
    """Start a case from a template; the first step's task is created at once.

    Any active employee may start a case, and so may an HR administrator.
    The service checks that; anyone else gets 403.

    Args:
        data: The template to run and what the case is about.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The new case, in progress.

    Raises:
        PermissionDeniedException: If the caller is neither HR nor an active employee.
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        WorkflowTemplateArchivedException: If the template has been archived.
        ValidationException: If the template has no steps.
    """
    service = InstanceService(db)
    instance = await service.start_instance(caller, data.template_id, data.subject)
    response = InstanceResponse.model_validate(instance)
    await db.commit()
    return response


@router.get("/workflow-instances", status_code=200)
async def list_instances(
    status: InstanceStatus | None = Query(default=None),
    template_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List the cases the caller may see, newest first.

    HR administrators and business executives see every case. Everyone else
    sees the cases they started, have a task in, or head a department that has
    a step in.

    Args:
        status: Only cases in this status (in_progress, completed, cancelled).
        template_id: Only cases of this template.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        A paginated response of cases.
    """
    service = InstanceService(db)
    result = await service.list_instances(caller, status, template_id, page, limit)
    result.data = [InstanceResponse.model_validate(instance) for instance in result.data]
    return result


@router.get("/workflow-instances/{instance_id}", status_code=200)
async def get_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> InstanceDetailResponse:
    """Get one case with its progress: the template's current steps and the tasks created so far.

    Args:
        instance_id: Id of the case.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The case, its steps in order and its tasks, oldest first.

    Raises:
        WorkflowInstanceNotFoundException: If it doesn't exist or the caller may not see it.
    """
    service = InstanceService(db)
    found = await service.get_instance(caller, instance_id)
    base = InstanceResponse.model_validate(found["instance"]).model_dump()
    return InstanceDetailResponse(
        **base,
        steps=[StepResponse.model_validate(step) for step in found["steps"]],
        tasks=[InstanceTaskResponse.model_validate(task) for task in found["tasks"]],
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

@router.post("/workflow-templates/{template_id}/steps", status_code=200)
async def add_step(
    template_id: uuid.UUID,
    data: StepCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> StepResponse:
    """Add a step to a template, at a chosen position or at the end.

    Requires the HR Administrator or Manager role. Adding in the middle moves
    the later steps down by one.

    Args:
        template_id: Template to add the step to.
        data: The step's name, department, optional assignee, turnaround and position.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The newly created step.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        DepartmentNotFoundException: If the department isn't in the caller's org.
        EmployeeNotFoundException: If the default assignee isn't an employee here.
        ValidationException: If the assignee was offboarded or the position is out of range.
    """
    service = StepService(db)
    step = await service.add_step(caller, template_id, data.model_dump())
    response = StepResponse.model_validate(step)
    await db.commit()
    return response


@router.get("/workflow-templates/{template_id}/steps", status_code=200)
async def list_steps(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> list[StepResponse]:
    """List a template's steps in order, first step first.

    Open to any authenticated member of the organization. Not paginated: a
    template has a handful of steps and a screen needs them all, in order.

    Args:
        template_id: Template whose steps to list.
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        The steps, in position order.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
    """
    service = StepService(db)
    steps = await service.list_steps(template_id)
    return [StepResponse.model_validate(step) for step in steps]


@router.put("/workflow-templates/{template_id}/steps/order", status_code=200)
async def reorder_steps(
    template_id: uuid.UUID,
    data: StepOrderRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> list[StepResponse]:
    """Put a template's steps in a new order.

    Requires the HR Administrator or Manager role. Send every step id of the
    template, in the order wanted. Refused while a case is running on the
    template.

    Args:
        template_id: Template whose steps to reorder.
        data: All of the template's step ids, in the new order.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The steps in their new order.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        ResourceInUseException: If a case is in progress on the template.
        ValidationException: If the ids are not exactly the template's steps.
    """
    service = StepService(db)
    steps = await service.reorder_steps(caller, template_id, data.step_ids)
    response = [StepResponse.model_validate(step) for step in steps]
    await db.commit()
    return response


@router.patch("/workflow-steps/{step_id}", status_code=200)
async def update_step(
    step_id: uuid.UUID,
    data: StepUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> StepResponse:
    """Change a step's name, department, default assignee or turnaround.

    Requires the HR Administrator or Manager role. Send only the fields to
    change; ``null`` on the assignee or turnaround clears it. Tasks already
    created from the step keep their deadlines.

    Args:
        step_id: Id of the step to change.
        data: Only the fields to change.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The updated step.

    Raises:
        WorkflowStepNotFoundException: If the step isn't in the caller's org.
        DepartmentNotFoundException: If the new department isn't in the caller's org.
        EmployeeNotFoundException: If the new default assignee isn't an employee here.
        ValidationException: If the new assignee was offboarded.
    """
    service = StepService(db)
    # exclude_unset keeps only the fields the client actually sent, so
    # "left out" (unchanged) and "sent as null" (clear it) stay different.
    step = await service.update_step(caller, step_id, data.model_dump(exclude_unset=True))
    response = StepResponse.model_validate(step)
    await db.commit()
    return response


@router.delete("/workflow-steps/{step_id}", status_code=200)
async def delete_step(
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> StepResponse:
    """Soft-delete a step; the later steps move up to close the gap.

    Requires the HR Administrator or Manager role. Blocked while a task
    created from the step is still open.

    Args:
        step_id: Id of the step to delete.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The deleted step (with the position it had).

    Raises:
        WorkflowStepNotFoundException: If the step isn't in the caller's org.
        ResourceInUseException: If a task created from it is still open.
    """
    service = StepService(db)
    step = await service.delete_step(caller, step_id)
    response = StepResponse.model_validate(step)
    await db.commit()
    return response


@router.post("/workflow-templates/{template_id}/archive", status_code=200)
async def archive_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> TemplateResponse:
    """Retire a template so it can't start new cases (running cases carry on).

    Requires the HR Administrator or Manager role.

    Args:
        template_id: Id of the template to archive.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The archived template.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        WorkflowTemplateAlreadyArchivedException: If it is already archived.
    """
    service = TemplateService(db)
    template = await service.archive_template(caller, template_id)
    response = TemplateResponse.model_validate(template)
    await db.commit()
    return response


@router.post("/workflow-templates/{template_id}/unarchive", status_code=200)
async def unarchive_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_BUILDER_ROLES)),
) -> TemplateResponse:
    """Bring an archived template back, so it can start cases again.

    Requires the HR Administrator or Manager role.

    Args:
        template_id: Id of the template to unarchive.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator or Manager.

    Returns:
        The template, no longer archived.

    Raises:
        WorkflowTemplateNotFoundException: If the template isn't in the caller's org.
        WorkflowTemplateNotArchivedException: If it is not archived.
    """
    service = TemplateService(db)
    template = await service.unarchive_template(caller, template_id)
    response = TemplateResponse.model_validate(template)
    await db.commit()
    return response
