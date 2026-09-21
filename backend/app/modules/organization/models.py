"""SQLAlchemy models for the organization structure module.

Defines locations, departments, positions, and employees. All models are
organization-scoped via an ``organization_id`` foreign key and
rely on Postgres row-level security (RLS) to restrict visibility to the
caller's current organization. Deletion is soft (a nullable ``deleted_at``
timestamp) rather than a hard row delete.
"""

from __future__ import annotations

import decimal
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    DECIMAL,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .enums import CriticalityType, EmployeeStatus, EmploymentType, RiskLevel
from app.core.database import BaseModel

if TYPE_CHECKING:
    from app.modules.tenancy_identity.models import Organization, User
    from app.modules.okrs.models import OKR


class Location(BaseModel):
    """A physical or logical site an organization operates from.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. Employees may optionally be assigned to a location.
    """

    __tablename__ = "locations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this location belongs to",
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Name of the location"
    )

    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Address of the location"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the location is deleted."
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="locations"
    )
    employees: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="location"
    )
    okrs: Mapped[list["OKR"]] = relationship(
        "OKR", back_populates="location"
    )


class Department(BaseModel):
    """An organizational department, optionally flagged as revenue-critical.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. Holds one or more positions; deletion is blocked while
    active positions still reference it (enforced in the service layer).
    """

    __tablename__ = "departments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this department belongs to"
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Name of the department"
    )

    is_critical: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether the department is critical"
    )

    revenue_allocation_percentage: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(6, 2),
        nullable=True,
        doc="Revenue allocation percentage — only meaningful when is_critical is true"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the department is deleted."
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="departments"
    )
    positions: Mapped[list["Position"]] = relationship(
        "Position", back_populates="department"
    )
    okrs: Mapped[list["OKR"]] = relationship(
        "OKR", back_populates="department"
    )


class Position(BaseModel):
    """A role within a department, forming a self-referential org-chart tree.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. ``reports_to_position_id`` links a position to its parent
    in the reporting hierarchy (nullable at the top of the chart). Deletion
    is blocked while active employees or direct reports still reference it
    (enforced in the service layer). ``risk_level`` and ``criticality_type``
    are constrained at the database level to the values of the ``RiskLevel``
    and ``CriticalityType`` enums.
    """

    __tablename__ = "positions"

    __table_args__ = (
        CheckConstraint(
            f"risk_level IN {tuple(r.value for r in RiskLevel)}",
            name="check_position_risk_level",
        ),
        CheckConstraint(
            f"criticality_type IN {tuple(c.value for c in CriticalityType)}",
            name="check_position_criticality_type",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this position belongs to"
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
        doc="Department this position belongs to"
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Title of the position"
    )

    is_critical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether the position is critical"
    )

    reports_to_position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("positions.id"),
        nullable=True,
        index=True,
        doc="Position this position reports to — structural org-chart shape, nullable at the top"
    )

    risk_level: Mapped[RiskLevel | None] = mapped_column(
        String(12),
        nullable=True,
        doc="Risk level of the position"
    )

    criticality_type: Mapped[CriticalityType | None] = mapped_column(
        String(30),
        nullable=True,
        doc="Criticality type of the position"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the position is deleted."
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="positions"
    )
    department: Mapped["Department"] = relationship(
        "Department", back_populates="positions"
    )
    reports_to: Mapped["Position | None"] = relationship(
        "Position", remote_side="Position.id", back_populates="direct_reports"
    )
    direct_reports: Mapped[list["Position"]] = relationship(
        "Position", back_populates="reports_to"
    )
    employees: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="position"
    )


class Employee(BaseModel):
    """A person holding a position within an organization.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. ``user_id`` is nullable since an employee record can
    exist before the person is invited to log in. ``manager_id`` is a
    self-referential foreign key capturing this person's actual manager,
    which may differ from the structural ``reports_to`` chain on their
    position. ``employment_type`` and ``status`` are constrained at the
    database level to the values of the ``EmploymentType`` and
    ``EmployeeStatus`` enums.
    """

    __tablename__ = "employees"

    __table_args__ = (
        Index("idx_employees_org_location", "organization_id", "location_id"),
        CheckConstraint(
            f"employment_type IN {tuple(e.value for e in EmploymentType)}",
            name="check_employee_employment_type",
        ),
        CheckConstraint(
            f"status IN {tuple(s.value for s in EmployeeStatus)}",
            name="check_employee_status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this employee belongs to"
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
        doc="User this employee is linked to — nullable, an employee can exist before being invited to log in"
    )

    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("positions.id"),
        nullable=False,
        index=True,
        doc="Position this employee holds"
    )

    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=True,
        index=True,
        doc="This specific person's actual manager"
    )

    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
        doc="Location of the employee"
    )

    employee_code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Display-friendly employee code, e.g. 'EMP-001' — not the real key"
    )

    first_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="First name of the employee"
    )

    last_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Last name of the employee"
    )

    work_email: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Work email of the employee"
    )

    phone_number: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Phone number of the employee"
    )

    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Employee's own address — distinct from locations.address (the office/site they work out of)"
    )

    employment_type: Mapped[EmploymentType | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Employment type of the employee"
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        doc="Start date of the employee"
    )

    status: Mapped[EmployeeStatus] = mapped_column(
        String(20),
        nullable=False,
        default=EmployeeStatus.ACTIVE.value,
        server_default=EmployeeStatus.ACTIVE.value,
        doc="Status of the employee"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the employee is deleted."
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="employees"
    )
    user: Mapped["User | None"] = relationship(
        "User", back_populates="employees"
    )
    position: Mapped["Position"] = relationship(
        "Position", back_populates="employees"
    )
    location: Mapped["Location | None"] = relationship(
        "Location", back_populates="employees"
    )
    manager: Mapped["Employee | None"] = relationship(
        "Employee", remote_side="Employee.id", back_populates="direct_reports"
    )
    direct_reports: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="manager"
    )
