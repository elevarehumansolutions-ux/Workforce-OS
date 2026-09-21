"""Pydantic request and response schemas for the Business DNA module."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Core value
# ---------------------------------------------------------------------------

class BusinessDNACoreValueCreateRequest(BaseModel):
    """Request body for adding a core value to the org's Business DNA profile.

    ``organization_id``/``business_dna_id`` are deliberately absent — the
    caller's own org has exactly one Business DNA profile, resolved
    server-side from the authenticated caller's membership, never supplied
    by the client.
    """

    value: str


class BusinessDNACoreValueUpdateRequest(BaseModel):
    """Request body for editing an existing core value."""

    value: str


class BusinessDNACoreValueResponse(BaseModel):
    """API representation of a single core value."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_dna_id: uuid.UUID
    value: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Business DNA
# ---------------------------------------------------------------------------

class BusinessDNAUpsertRequest(BaseModel):
    """Request body for ``PUT /business-dna``.

    One schema, not a Create/Update pair — this resource only ever has one
    write endpoint (``PUT``, upsert), unlike departments/positions/etc.
    which have separate ``POST``/``PATCH`` verbs. ``organization_id`` is
    deliberately absent, same reasoning as the core-value request above.

    ``organization_name`` is folded in here rather than a separate
    endpoint, so the service can set ``organizations.name`` and upsert this
    profile in one transaction — see 08_DECISIONS.md 2026-09-21. Every
    field is optional since the onboarding wizard can be filled in and
    saved incrementally, matching the underlying columns, which are all
    nullable.
    """

    organization_name: str | None = None
    industry: str | None = None
    products_services_description: str | None = None
    vision: str | None = None
    mission: str | None = None
    business_model: str | None = None
    performance_philosophy: str | None = None
    workforce_rules: str | None = None
    revenue_drivers: str | None = None
    operational_drivers: str | None = None
    customer_value_drivers: str | None = None
    capital_investment_amount: Decimal | None = None


class BusinessDNAResponse(BaseModel):
    """API representation of an org's Business DNA profile.

    ``capital_investment_amount`` is field-restricted to
    hr_administrator/business_executive (08_DECISIONS.md 2026-09-21) — the
    service/router layer is responsible for nulling it out for other roles
    before returning this schema; it isn't something this schema can decide
    on its own since Pydantic has no notion of the caller's role.

    ``organization_name`` isn't a column on ``business_dna`` (it lives on
    ``organizations.name``) — the service populates it from the
    ``organization`` relationship when building this response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str | None = None
    industry: str | None = None
    products_services_description: str | None = None
    vision: str | None = None
    mission: str | None = None
    business_model: str | None = None
    performance_philosophy: str | None = None
    workforce_rules: str | None = None
    revenue_drivers: str | None = None
    operational_drivers: str | None = None
    customer_value_drivers: str | None = None
    capital_investment_amount: Decimal | None = None
    core_values: list[BusinessDNACoreValueResponse] = []
    created_at: datetime
    updated_at: datetime
