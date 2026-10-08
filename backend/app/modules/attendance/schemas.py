"""Pydantic request and response schemas for the attendance module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .enums import AttendanceClosedBy


class AttendanceRecordResponse(BaseModel):
    """API representation of one clock-in/clock-out record.

    ``clock_out_at`` null means the employee is currently clocked in.
    ``closed_by`` of ``system`` marks a record the nightly auto-close ended:
    its ``clock_out_at`` is the organization's midnight cutoff, not
    something the employee did, and ``close_reason`` says why.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    employee_id: uuid.UUID
    clock_in_at: datetime
    clock_out_at: datetime | None
    closed_by: AttendanceClosedBy | None
    close_reason: str | None
    created_at: datetime
    updated_at: datetime


class ClockInResponse(BaseModel):
    """Result of ``POST /attendance/clock-in``.

    ``already_clocked_in`` tells "you just clocked in" (false) from "you
    already were; this is your existing record" (true), so a client can say
    the right thing instead of a misleading "Clocked in!".
    """

    already_clocked_in: bool
    record: AttendanceRecordResponse
