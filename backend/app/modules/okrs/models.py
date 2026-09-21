"""ORM models for Cluster 4 (Strategy): OKRs.

Contains:
- :class:`OKR`: a corporate or departmental objective, optionally scoped to
  one location.
- :class:`KeyResult`: one measurable result belonging to an :class:`OKR`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel

if TYPE_CHECKING:
    from app.modules.organization.models import Department, Location
    from app.modules.tenancy_identity.models import Organization


class OKR(BaseModel):
    """A corporate or departmental objective.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable. ``department_id`` null means a corporate objective, set
    means departmental. ``location_id`` null means the objective applies
    org/department-wide; set scopes it to one location (the branch/store
    model). Adding an objective is always additive — existing rows are never
    cleared or replaced by a later one, this falls out of the schema with no
    extra logic needed.
    """

    __tablename__ = "okrs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this OKR belongs to",
    )

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=True,
        index=True,
        doc="Department this OKR is scoped to; null means a corporate OKR",
    )

    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id"),
        nullable=True,
        index=True,
        doc=(
            "Location this OKR is scoped to; null means it applies "
            "org/department-wide"
        ),
    )

    title: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Title of the objective"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the OKR is deleted.",
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="okrs"
    )
    department: Mapped["Department | None"] = relationship(
        "Department", back_populates="okrs"
    )
    location: Mapped["Location | None"] = relationship(
        "Location", back_populates="okrs"
    )
    key_results: Mapped[list["KeyResult"]] = relationship(
        "KeyResult", back_populates="okr"
    )


class KeyResult(BaseModel):
    """A single measurable result belonging to an :class:`OKR`.

    Organization-scoped (RLS restricts rows to the caller's current org) and
    soft-deletable.
    """

    __tablename__ = "key_results"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this key result belongs to",
    )

    okr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("okrs.id"),
        nullable=False,
        index=True,
        doc="OKR this key result belongs to",
    )

    description: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Description of the key result"
    )

    target_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, doc="Target date for this key result"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Soft delete timestamp: non-null means the key result is deleted.",
    )

    # Relationships
    okr: Mapped["OKR"] = relationship("OKR", back_populates="key_results")
