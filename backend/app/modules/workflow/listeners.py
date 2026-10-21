"""The Workflow module's side of the notice board (app/core/events.py).

The Task module announces "a task was completed" or "a task was cancelled".
These two functions are how the Workflow module hears about it. A task that
does not belong to a workflow case is ignored.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events

from .service import InstanceService


async def on_task_completed(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    organization_id: uuid.UUID,
    workflow_instance_id: uuid.UUID | None,
    workflow_step_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    """A task was completed: move its case on to the next step."""
    if workflow_instance_id is None:
        return
    await InstanceService(db).move_on_after_task(
        instance_id=workflow_instance_id,
        finished_step_id=workflow_step_id,
        finished_task_id=task_id,
        actor_user_id=actor_user_id,
    )


async def on_task_cancelled(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    organization_id: uuid.UUID,
    workflow_instance_id: uuid.UUID | None,
    workflow_step_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    reason: str,
) -> None:
    """A task was cancelled: skip that step and move its case on."""
    if workflow_instance_id is None:
        return
    await InstanceService(db).move_on_after_task(
        instance_id=workflow_instance_id,
        finished_step_id=workflow_step_id,
        finished_task_id=task_id,
        actor_user_id=actor_user_id,
        skipped_reason=reason,
    )


def register_listeners() -> None:
    """Sign the Workflow module up for task events. Safe to call more than once."""
    events.subscribe(events.TASK_COMPLETED, on_task_completed)
    events.subscribe(events.TASK_CANCELLED, on_task_cancelled)
