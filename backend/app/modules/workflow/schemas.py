"""Pydantic request and response schemas for the Workflow module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

class TemplateCreateRequest(BaseModel):
    """Request body for creating a workflow template.

    ``organization_id`` is deliberately absent: it comes from the caller's
    membership, never from the client. Steps are added afterwards, one at a
    time, through their own endpoint.
    """

    # Spaces around the name are removed first, so "   " counts as empty.
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    department_id: uuid.UUID


class TemplateUpdateRequest(BaseModel):
    """Request body for editing a template. Send only the fields to change.

    A field left out is left as it is. Sending ``null`` for either field is a
    422, not "clear it": both columns are required. (The fields are typed
    without ``| None`` for that reason; the ``None`` default only means "not
    sent", and Pydantic does not validate defaults.)
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(default=None, min_length=1, max_length=200)
    department_id: uuid.UUID = None


class TemplateResponse(BaseModel):
    """API representation of a template, returned by the template endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID
    name: str
    created_by_user_id: uuid.UUID | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------

class StepCreateRequest(BaseModel):
    """Request body for adding a step to a template.

    ``step_order`` is the position the step should take (1 = first). Leave it
    out to add the step at the end. Adding in the middle moves the later
    steps down by one. ``default_assignee_employee_id`` and
    ``default_turnaround_hours`` may be left out: the task then lands in the
    department's queue and/or has no deadline.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    department_id: uuid.UUID
    default_assignee_employee_id: uuid.UUID | None = None
    default_turnaround_hours: int | None = Field(default=None, gt=0)
    step_order: int | None = Field(default=None, ge=1)


class StepUpdateRequest(BaseModel):
    """Request body for editing a step. Send only the fields to change.

    A field left out is left as it is. For ``default_assignee_employee_id``
    and ``default_turnaround_hours``, sending ``null`` means "clear it" (no
    default assignee, no deadline). ``name`` and ``department_id`` are
    required on a step, so ``null`` there is a 422 (typed without ``| None``;
    the ``None`` default only means "not sent"). The position is not edited
    here: moving steps is the reorder action.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(default=None, min_length=1, max_length=200)
    department_id: uuid.UUID = None
    default_assignee_employee_id: uuid.UUID | None = None
    default_turnaround_hours: int | None = Field(default=None, gt=0)


class StepOrderRequest(BaseModel):
    """Request body for reordering a template's steps.

    ``step_ids`` is every step of the template, in the order it should have:
    the first id becomes step 1, the next step 2, and so on.
    """

    step_ids: list[uuid.UUID]


class StepResponse(BaseModel):
    """API representation of a step, returned by the step endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    workflow_template_id: uuid.UUID
    step_order: int
    name: str
    department_id: uuid.UUID
    default_assignee_employee_id: uuid.UUID | None
    default_turnaround_hours: int | None
    created_at: datetime
    updated_at: datetime
