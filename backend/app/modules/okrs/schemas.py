"""Pydantic request and response schemas for the OKR module."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# OKR
# ---------------------------------------------------------------------------

class OKRCreateRequest(BaseModel):
    """Request body for creating an OKR.

    ``organization_id`` is deliberately absent — resolved server-side from
    the authenticated caller's membership, never supplied by the client.
    ``department_id`` omitted/null means a corporate OKR; ``location_id``
    omitted/null means it applies org/department-wide.
    """

    title: str
    department_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None


class OKRUpdateRequest(BaseModel):
    """Request body for partially updating an OKR. All fields optional."""

    title: str | None = None
    department_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None


class OKRResponse(BaseModel):
    """API representation of an OKR, returned by OKR endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID | None
    location_id: uuid.UUID | None
    title: str
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Key result
# ---------------------------------------------------------------------------

class KeyResultCreateRequest(BaseModel):
    """Request body for adding a key result to an OKR.

    ``organization_id``/``okr_id`` are deliberately absent — resolved
    server-side from the URL path and the parent OKR, never supplied by
    the client.
    """

    description: str
    target_date: date | None = None


class KeyResultUpdateRequest(BaseModel):
    """Request body for partially updating a key result. All fields optional."""

    description: str | None = None
    target_date: date | None = None


class KeyResultResponse(BaseModel):
    """API representation of a key result, returned by key result endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    okr_id: uuid.UUID
    description: str
    target_date: date | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
