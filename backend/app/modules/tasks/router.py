"""FastAPI routes for the Task module.

Create, list, read, edit, complete, cancel and reassign tasks. Any authenticated member can
call these; what each caller may actually do or see is decided in
``TaskService`` (HR, the ``manager`` role and department heads create; an
assignee sees and completes their own; HR and executives see everything).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db
from app.core.exceptions import ValidationException
from app.core.schemas import PaginationResponse
from app.modules.tenancy_identity.models import Membership

from .enums import TaskStatus
from .schemas import (
    TaskCancelRequest,
    TaskCreateRequest,
    TaskReassignRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from .service import TaskService

router = APIRouter()


@router.post("/tasks", status_code=200)
async def create_task(
    data: TaskCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TaskResponse:
    """Create a task.

    Allowed to HR administrators, members with the ``manager`` role, and the
    head of the task's department. A creator from another department cannot
    choose the assignee: the task goes to the work department's head (or stays
    unassigned, with HR told, if it has none).

    Args:
        data: The task to create.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The created task.

    Raises:
        PermissionDeniedException: If the caller may not create tasks (403).
        DepartmentNotFoundException: If the department isn't in the org (404).
        EmployeeNotFoundException: If the assignee isn't an employee here (404).
        KPINotFoundException: If the KPI isn't in the org (404).
        ValidationException: If an outsider names an assignee, or the assignee
            is offboarded (422).
    """
    task = await TaskService(db).create_task(caller, data.model_dump())
    await db.commit()
    return TaskResponse.model_validate(task)


@router.get("/tasks", status_code=200)
async def list_tasks(
    department_id: uuid.UUID | None = Query(default=None),
    assigned_to_employee_id: uuid.UUID | None = Query(default=None),
    status: TaskStatus | None = Query(default=None),
    kpi_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> PaginationResponse:
    """List the tasks the caller may see, newest first.

    HR administrators and business executives see every task. Others see
    tasks assigned to them, tasks they created, and tasks of the departments
    they head (or, for the ``manager`` role, their own department).

    Args:
        department_id: Only tasks for this department.
        assigned_to_employee_id: Only tasks assigned to this employee.
        status: Only tasks in this status.
        kpi_id: Only tasks linked to this KPI.
        page: 1-indexed page number.
        limit: Maximum number of rows per page (1-100).
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        A paginated response of tasks.
    """
    result = await TaskService(db).list_tasks(
        caller, department_id, assigned_to_employee_id, status, kpi_id, page, limit
    )
    result.data = [TaskResponse.model_validate(task) for task in result.data]
    return result


@router.get("/tasks/{task_id}", status_code=200)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TaskResponse:
    """Get one task the caller is allowed to see.

    Args:
        task_id: Id of the task.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The task.

    Raises:
        TaskNotFoundException: If it doesn't exist, or exists but is outside
            the caller's view (the same 404, so its existence isn't revealed).
    """
    return TaskResponse.model_validate(await TaskService(db).get_task(caller, task_id))


@router.patch("/tasks/{task_id}", status_code=200)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TaskResponse:
    """Edit a task's title, description, deadline or KPI link.

    Allowed to HR, the department's head and the task's creator, not the
    assignee. ``status``, the assignee and the department cannot be changed
    here (unknown fields are rejected). Changing ``due_at`` is audit-logged.

    Args:
        task_id: Id of the task.
        data: Fields to change; at least one is required.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The updated task.

    Raises:
        TaskNotFoundException: If it doesn't exist or is outside the caller's view (404).
        PermissionDeniedException: If the caller may see but not edit it (403).
        TaskNotOpenException: If it is already completed or cancelled (409).
        KPINotFoundException: If the KPI isn't in the org (404).
        ValidationException: If no field is provided (422).
    """
    if not data.has_updates():
        raise ValidationException(message="Provide at least one field to update")
    task = await TaskService(db).update_task(caller, task_id, data.model_dump(exclude_unset=True))
    await db.commit()
    return TaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/complete", status_code=200)
async def complete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TaskResponse:
    """Mark a task completed.

    Allowed to the assignee, the department's head and HR. Not idempotent:
    completing a task twice is a 409 and the first completion time stands.

    Args:
        task_id: Id of the task.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The completed task.

    Raises:
        TaskNotFoundException: If it doesn't exist or is outside the caller's view (404).
        PermissionDeniedException: If the caller may see but not complete it (403).
        TaskNotOpenException: If it is already completed or cancelled (409).
    """
    task = await TaskService(db).complete_task(caller, task_id)
    await db.commit()
    return TaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/cancel", status_code=200)
async def cancel_task(
    task_id: uuid.UUID,
    data: TaskCancelRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TaskResponse:
    """Cancel a task that is no longer needed.

    Allowed to HR, the department's head and the task's creator, not the
    assignee. A reason is required. Final: a cancelled task counts as
    neither completed nor late, and a completed task can't be cancelled.

    Args:
        task_id: Id of the task.
        data: The reason (required, up to 500 characters).
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The cancelled task, with ``cancel_reason`` set.

    Raises:
        TaskNotFoundException: If it doesn't exist or is outside the caller's view (404).
        PermissionDeniedException: If the caller may see but not cancel it (403).
        TaskNotOpenException: If it is already completed or cancelled (409).
    """
    task = await TaskService(db).cancel_task(caller, task_id, data.reason)
    await db.commit()
    return TaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/reassign", status_code=200)
async def reassign_task(
    task_id: uuid.UUID,
    data: TaskReassignRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> TaskResponse:
    """Give a task to a (different) employee, with a new deadline.

    Also how an unassigned task gets its first assignee. Both the new
    assignee and a new future ``due_at`` are required, every time. The status
    goes back to ``open``. Allowed to HR, the department's head, and the
    creator when they work in the task's department.

    Args:
        task_id: Id of the task.
        data: The new assignee and the new deadline.
        db: Database session dependency.
        caller: Caller's membership.

    Returns:
        The reassigned task.

    Raises:
        TaskNotFoundException: If it doesn't exist or is outside the caller's view (404).
        PermissionDeniedException: If the caller may see but not reassign it (403).
        EmployeeNotFoundException: If the new assignee isn't an employee here (404).
        TaskNotOpenException: If it is already completed or cancelled (409).
        TaskChangedException: If somebody else reassigned it at the same moment (409).
        ValidationException: If ``due_at`` isn't in the future, the person already
            has the task, or has been offboarded (422).
    """
    task = await TaskService(db).reassign_task(
        caller, task_id, data.assigned_to_employee_id, data.due_at
    )
    await db.commit()
    return TaskResponse.model_validate(task)
