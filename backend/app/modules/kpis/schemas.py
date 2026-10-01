"""Pydantic request and response schemas for the KPI module."""

import decimal
import uuid
from datetime import datetime, date

from pydantic import BaseModel, ConfigDict

from .enums import KPITrackingMode

class KPICreate(BaseModel):
    """Request body for creating a KPI.

    ``organization_id`` is deliberately absent — resolved server-side
    from the authenticated caller's membership, never supplied by the
    client. ``tracking_mode`` is also absent: it defaults to ``'manual'``
    at the database level, and nothing about creating a KPI through this
    endpoint needs the caller to choose ``'task_count'`` yet.
    """

    department_id: uuid.UUID
    location_id: uuid.UUID | None = None
    key_result_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    weight: decimal.Decimal
    is_inverse: bool = False
    target_value: decimal.Decimal | None = None
    unit: str | None = None

class KPIResponse(BaseModel):
    """API representation of a KPI, returned by KPI endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID
    location_id: uuid.UUID | None
    key_result_id: uuid.UUID | None
    name: str
    description: str | None
    weight: decimal.Decimal
    is_inverse: bool
    target_value: decimal.Decimal | None
    unit: str | None
    tracking_mode: KPITrackingMode
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KPIUpdate(BaseModel):
    """Request body for partially updating a KPI. All fields optional.

    ``department_id``/``location_id`` are deliberately absent — those
    define which weight group a KPI belongs to, and moving a KPI between
    groups isn't a plain edit (it would need to re-validate the new
    group's total too, which nothing asked for).
    """

    name: str | None = None
    description: str | None = None
    weight: decimal.Decimal | None = None
    is_inverse: bool | None = None
    target_value: decimal.Decimal | None = None
    unit: str | None = None
    key_result_id: uuid.UUID | None = None


class KPIGroupItem(BaseModel):
    """One KPI in a department/location group's desired end-state.

    ``id`` present means update an existing KPI; absent means this is a
    new one to create. An existing KPI whose id doesn't appear anywhere
    in the submitted list is deleted — that's the service's job to work
    out by comparing against what currently exists, not something
    represented on this schema itself.
    """

    id: uuid.UUID | None = None
    name: str
    description: str | None = None
    weight: decimal.Decimal
    is_inverse: bool = False
    target_value: decimal.Decimal | None = None
    unit: str | None = None
    key_result_id: uuid.UUID | None = None


class KPIGroupUpdateRequest(BaseModel):
    """Request body for PUT /departments/{id}/kpis — the whole group at once."""

    kpis: list[KPIGroupItem]


class KPIGroupUpdateResponse(BaseModel):
    """Response body: the full resulting list, real ids included."""
    kpis: list[KPIResponse]


class KPIScoreCreate(BaseModel):
    """Request body for POST /kpis/{id}/scores."""

    period_start: date
    period_end: date
    actual_value: decimal.Decimal


class KPIScoreResponse(BaseModel):
    """API representation of a KPI score, returned by scores endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    kpi_id: uuid.UUID
    period_start: date
    period_end: date
    actual_value: decimal.Decimal | None
    score_percentage: decimal.Decimal | None
    created_at: datetime
    updated_at: datetime

