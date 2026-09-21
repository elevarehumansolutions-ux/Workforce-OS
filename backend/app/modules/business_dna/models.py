"""ORM models for Cluster 3: Business DNA.

Contains:
- :class:`BusinessDNA`: an organization's single Business DNA profile.
- :class:`BusinessDNACoreValue`: one core value statement belonging to a
  Business DNA profile.
"""

from __future__ import annotations

import decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DECIMAL, UUID, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import BaseModel

if TYPE_CHECKING:
    from app.modules.tenancy_identity.models import Organization


class BusinessDNA(BaseModel):
    """An organization's Business DNA profile.

    One row per organization (enforced via a unique constraint on
    ``organization_id``), capturing the narrative fields — industry,
    vision, mission, business model, and drivers of revenue, operations,
    and customer value — that describe how the business operates. Related
    to a list of :class:`BusinessDNACoreValue` rows.
    """

    __tablename__ = "business_dna"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        unique=True,
        doc="Organization this Business DNA profile belongs to — one row per org",
    )

    industry: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Industry the business operates in"
    )

    products_services_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Description of the org's products and services"
    )

    vision: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Vision statement"
    )

    mission: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Mission statement"
    )

    business_model: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Description of how the business creates and captures value",
    )

    performance_philosophy: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="How the org thinks about and drives performance"
    )

    workforce_rules: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Workforce rules/policies narrative"
    )

    revenue_drivers: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="What drives revenue for this business"
    )

    operational_drivers: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="What drives operational efficiency/output"
    )

    customer_value_drivers: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="What drives value for the org's customers"
    )

    capital_investment_amount: Mapped[decimal.Decimal | None] = mapped_column(
        DECIMAL(14, 2),
        nullable=True,
        doc=(
            "Capital investment figure feeding department revenue-target "
            "allocation (Cluster 4) — field-restricted to hr_administrator/"
            "business_executive at the API layer, see 08_DECISIONS.md "
            "2026-09-21"
        ),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="business_dna"
    )
    core_values: Mapped[list["BusinessDNACoreValue"]] = relationship(
        "BusinessDNACoreValue", back_populates="business_dna"
    )


class BusinessDNACoreValue(BaseModel):
    """A single core value statement belonging to a Business DNA profile.

    Each row holds one core value and links back to both its parent
    :class:`BusinessDNA` profile and the owning organization.
    """

    __tablename__ = "business_dna_core_values"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        doc="Organization this core value belongs to",
    )

    business_dna_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_dna.id"),
        nullable=False,
        index=True,
        doc="Business DNA profile this core value belongs to",
    )

    value: Mapped[str] = mapped_column(
        Text, nullable=False, doc="A single core value statement"
    )

    # Relationships
    business_dna: Mapped["BusinessDNA"] = relationship(
        "BusinessDNA", back_populates="core_values"
    )
