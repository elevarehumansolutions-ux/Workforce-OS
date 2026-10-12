"""ORM models for Cluster 6 (Workflow).

Contains :class:`WorkflowTemplate` (a named process), :class:`WorkflowStep`
(one step in it) and :class:`WorkflowInstance` (one running case).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseModel
from .enums import InstanceStatus


class WorkflowTemplate(BaseModel):
    """A named, reusable process, such as "Client Onboarding".

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. The steps live in :class:`WorkflowStep`; this row is only
    the name and who owns it.

    ``department_id`` is the department that owns the template. It can differ
    from the departments of its steps: an onboarding template owned by HR can
    still have a step in Finance and another in Legal.

    ``archived_at`` retires a template without deleting it: an archived
    template can't be used to start new cases, but cases already running on it
    carry on. A template can't be deleted while a case is running on it.
    There are no ORM relationships on this model, deliberately: the service
    layer does its own lookups, which avoids lazy-load surprises under the
    async session (same choice as the Task module).
    See 08_DECISIONS.md 2026-10-12.
    """

    __tablename__ = "workflow_templates"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this template belongs to",
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
        doc="Department that owns the template (its steps may be in other departments)",
    )

    name: Mapped[str] = mapped_column(
        Text, nullable=False, doc="What the process is called, e.g. 'Client Onboarding'"
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        doc="Who built the template",
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="When it was retired; null = available for starting new cases",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, doc="Soft-delete timestamp"
    )


class WorkflowStep(BaseModel):
    """One step of a template: who does it and how long they get.

    Example: step 2 of "Client Onboarding" is "Finance review", in the Finance
    department, 24 business hours, default assignee Tunde. When the step before
    it finishes, the system creates a task from this row.

    ``step_order`` is a plain 1, 2, 3 sequence (no branching or parallel steps
    in the MVP). It is not unique in the database on purpose: adding a step in
    the middle shifts the later ones, and the service keeps the numbers
    sensible. The same department may appear in several steps.

    ``default_assignee_employee_id`` is only a pre-fill used when the task is
    created; if that person has left, the task is created unassigned.
    ``default_turnaround_hours`` is used once, to work out the task's ``due_at``
    when it is created (business hours); empty means the task has no deadline.
    Soft-deletable, but a step with an open task can't be deleted.
    See 08_DECISIONS.md 2026-10-12.
    """

    __tablename__ = "workflow_steps"

    __table_args__ = (
        CheckConstraint(
            "default_turnaround_hours IS NULL OR default_turnaround_hours > 0",
            name="check_workflow_step_turnaround_positive",
        ),
        CheckConstraint("step_order >= 1", name="check_workflow_step_order_positive"),
        Index("idx_workflow_steps_template_order", "workflow_template_id", "step_order"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this step belongs to",
    )

    workflow_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_templates.id"),
        nullable=False,
        doc="Template this step is part of",
    )

    step_order: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Position in the template, starting at 1"
    )

    name: Mapped[str] = mapped_column(
        Text, nullable=False, doc="What the step is called, e.g. 'Finance review'"
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
        doc="Department that does this step (can differ from the template's own)",
    )

    default_assignee_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=True,
        doc="Person who gets the task automatically; null = lands in the department queue",
    )

    default_turnaround_hours: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Business hours allowed for the step; null = the task has no deadline",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, doc="Soft-delete timestamp"
    )


class WorkflowInstance(BaseModel):
    """One running case of a template, such as "Zenith Ltd onboarding".

    ``subject`` is what the case is about (a client's name, say). The tasks it
    creates point back here through ``tasks.workflow_instance_id``. There is no
    "current step" column: what comes next is worked out from the template at
    the moment a task finishes (08_DECISIONS.md 2026-10-12).

    Organization-scoped (RLS). Not soft-deletable: a finished or cancelled case
    is permanent history (04_DATABASE.md). ``completed_at`` is set exactly when
    the status is ``completed``, and ``cancel_reason`` exactly when it is
    ``cancelled``, each enforced by a CHECK.
    """

    __tablename__ = "workflow_instances"

    __table_args__ = (
        CheckConstraint(
            f"status IN {tuple(s.value for s in InstanceStatus)}",
            name="check_workflow_instance_status",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL)"
            " OR (status <> 'completed' AND completed_at IS NULL)",
            name="check_workflow_instance_completed_at_matches_status",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancel_reason IS NOT NULL)"
            " OR (status <> 'cancelled' AND cancel_reason IS NULL)",
            name="check_workflow_instance_cancel_reason_matches_status",
        ),
        # Answers "is any case still running on this template?" for the
        # delete and reorder rules.
        Index(
            "idx_workflow_instances_template_status",
            "organization_id",
            "workflow_template_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this case belongs to",
    )

    workflow_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_templates.id"),
        nullable=False,
        doc="The process this case is running",
    )

    subject: Mapped[str] = mapped_column(
        Text, nullable=False, doc="What the case is about, e.g. a client's name"
    )

    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        doc="Who started the case; they may cancel it and are told when a step is skipped",
    )

    status: Mapped[InstanceStatus] = mapped_column(
        String(20),
        nullable=False,
        default=InstanceStatus.IN_PROGRESS.value,
        server_default=InstanceStatus.IN_PROGRESS.value,
        doc="in_progress, completed or cancelled",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="When the case was started",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the last step finished; set exactly when status is 'completed'",
    )

    cancel_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Why the case was stopped; set exactly when status is 'cancelled'",
    )
