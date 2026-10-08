"""ORM models for Cluster 7 (Attendance).

Contains :class:`AttendanceRecord` — one clock-in/clock-out pair for one
employee.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UUID, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel
from .enums import AttendanceClosedBy

if TYPE_CHECKING:
    from app.modules.organization.models import Employee
    from app.modules.tenancy_identity.models import Organization


class AttendanceRecord(BaseModel):
    """One clock-in/clock-out pair for one employee.

    Organization-scoped (RLS restricts rows to the caller's current org).
    Not soft-deletable: a record is a historical fact, and a mistaken one is
    corrected, not erased.

    "Currently clocked in" is derived, never stored: it means the employee's
    record has ``clock_out_at IS NULL``. A partial unique index allows at
    most one such open record per employee, so two simultaneous clock-ins
    can't both succeed — the database refuses the second, whatever the
    application code does. An employee can still have any number of
    *closed* records.

    ``closed_by`` and ``close_reason`` are null while the record is open and
    set together with ``clock_out_at`` when it closes. ``closed_by = 'system'``
    marks an auto-closed record whose clock-out time is the midnight cutoff,
    not something the employee did. See 08_DECISIONS.md 2026-10-01.
    """

    __tablename__ = "attendance_records"

    __table_args__ = (
        Index(
            "uq_attendance_one_open_per_employee",
            "employee_id",
            unique=True,
            postgresql_where=text("clock_out_at IS NULL"),
        ),
        Index(
            "idx_attendance_employee_clock_in",
            "organization_id",
            "employee_id",
            "clock_in_at",
        ),
        CheckConstraint(
            f"closed_by IN {tuple(c.value for c in AttendanceClosedBy)}",
            name="check_attendance_closed_by",
        ),
        CheckConstraint(
            "(clock_out_at IS NULL AND closed_by IS NULL AND close_reason IS NULL)"
            " OR (clock_out_at IS NOT NULL AND closed_by IS NOT NULL)",
            name="check_attendance_closed_fields_together",
        ),
        CheckConstraint(
            "clock_out_at IS NULL OR clock_out_at >= clock_in_at",
            name="check_attendance_out_after_in",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this record belongs to",
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
        doc="Employee who clocked in",
    )

    clock_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="When the employee clocked in",
    )

    clock_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the record ended; null means the employee is currently clocked in",
    )

    closed_by: Mapped[AttendanceClosedBy | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Who ended the record: 'employee' (clocked out) or 'system' (auto-closed at midnight); null while open",
    )

    close_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Why the system closed it, e.g. the employee did not clock out; null for an employee clock-out",
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    employee: Mapped["Employee"] = relationship("Employee")
