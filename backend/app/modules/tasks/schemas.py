"""Pydantic request and response schemas for the Task module."""

import decimal
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import BlockCategory, ReviewStatus, TaskStatus


def _require_timezone(value: datetime | None) -> datetime | None:
    """Reject a deadline with no timezone: it would be silently read in the server's."""
    if value is not None and value.tzinfo is None:
        raise ValueError("must include a timezone, e.g. 2026-10-09T17:00:00+01:00")
    return value


def _clean_title(value: str | None) -> str:
    """Trim a title and refuse an empty or null one."""
    if value is None:
        raise ValueError("title cannot be null")
    value = value.strip()
    if not value:
        raise ValueError("title cannot be empty")
    return value


class TaskCreateRequest(BaseModel):
    """Request body for creating a task.

    ``department_id`` is the department that does the work, which can differ
    from the creator's own. Leave ``assigned_to_employee_id`` out to put the
    task in the department queue; a creator from another department must
    leave it out, and the task then goes to that department's head.
    """

    department_id: uuid.UUID
    title: str = Field(max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    kpi_id: uuid.UUID | None = None
    assigned_to_employee_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str:
        """Trim the title and refuse an empty or null one."""
        return _clean_title(value)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime | None) -> datetime | None:
        """Require the deadline to carry a timezone."""
        return _require_timezone(value)


class TaskUpdateRequest(BaseModel):
    """Request body for partially updating a task. All fields optional.

    Deliberately excludes ``status``, ``completed_at``, ``assigned_to_employee_id``
    and ``department_id``: completing, cancelling and reassigning are their own
    actions (08_DECISIONS.md 2026-10-07), and moving a task to another
    department means creating a new one. Unknown fields are rejected with a
    422 rather than silently ignored, so a client that tries to send ``status``
    here finds out immediately.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    kpi_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str:
        """Trim the title and refuse an empty or null one."""
        return _clean_title(value)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime | None) -> datetime | None:
        """Require the deadline to carry a timezone."""
        return _require_timezone(value)

    def has_updates(self) -> bool:
        """Return whether any field was explicitly set on this request."""
        return self.model_dump(exclude_unset=True) != {}


class TaskCancelRequest(BaseModel):
    """Request body for cancelling a task. A reason is always required."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Trim the reason and refuse an empty one."""
        value = value.strip()
        if not value:
            raise ValueError("reason cannot be empty")
        return value


class TaskReassignRequest(BaseModel):
    """Request body for (re)assigning a task.

    Both fields are required: every reassignment needs a new deadline so the
    new assignee gets a fair clock (08_DECISIONS.md 2026-10-07). The deadline
    must also be in the future, which the service checks.
    """

    model_config = ConfigDict(extra="forbid")

    assigned_to_employee_id: uuid.UUID
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime) -> datetime:
        """Require the new deadline to carry a timezone."""
        return _require_timezone(value)


class TaskBlockRequest(BaseModel):
    """Request body for marking a task blocked: why, in a category and in words."""

    # Spaces are trimmed before the length check, so "   " counts as empty.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: BlockCategory
    reason: str = Field(min_length=1, max_length=500)


class TaskBlockResponse(BaseModel):
    """API representation of a block (one blocked period of a task and its review)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID
    blocked_by_user_id: uuid.UUID
    category: BlockCategory
    reason: str
    blocked_at: datetime
    unblocked_at: datetime | None
    review_status: ReviewStatus
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KPITaskProgressResponse(BaseModel):
    """Live progress of a task-count KPI: completed linked tasks in the current fiscal quarter.

    Nothing is stored: the count is made when asked. ``score_percentage`` is
    ``None`` when it can't be worked out (no target set, or a zero divisor).
    """

    kpi_id: uuid.UUID
    period_start: date
    period_end: date  # the last day of the quarter, inclusive
    completed_tasks: int
    target_value: decimal.Decimal | None
    unit: str | None
    score_percentage: decimal.Decimal | None


class TaskBlockReviewItem(TaskBlockResponse):
    """One block in a reviewer's list, with the task details a reviewer needs.

    A reviewer (for example the blocker's reporting manager) may not be allowed
    to open the task itself, so the task's title, department and deadline come
    along here.
    """

    task_title: str
    task_department_id: uuid.UUID
    task_due_at: datetime | None


class TaskResponse(BaseModel):
    """API representation of a task, returned by the task endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    workflow_instance_id: uuid.UUID | None
    workflow_step_id: uuid.UUID | None
    department_id: uuid.UUID
    kpi_id: uuid.UUID | None
    assigned_to_employee_id: uuid.UUID | None
    title: str
    description: str | None
    due_at: datetime | None
    completed_at: datetime | None
    cancel_reason: str | None
    status: TaskStatus
    # Not a database column: "overdue" is worked out when the response is built
    # (see tasks/overdue.py), so the default here is only a placeholder.
    overdue: bool = False
    # Null unless the task is blocked right now.
    blocked_since: datetime | None
    # Total blocked time a reviewer approved; it pushes the overdue moment later.
    approved_blocked_seconds: int
    created_by_user_id: uuid.UUID | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
