"""Pydantic schemas for the blueprint module.

Two groups: what Claude must answer with (``Proposed*``, ``BlueprintAnswer``)
and what the API sends and receives.
"""

import decimal
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# What Claude answers with
# ---------------------------------------------------------------------------
# Claude never sees database ids. New things get labels it invents (D1, P1,
# O1); things the company already has are shown to it as ED1..., EP1... and it
# must point at those labels, so nothing it says can reach a real row we did
# not show it.


class ProposedDepartment(BaseModel):
    """A department the company should have."""

    ref: str
    name: str
    rationale: str


class ProposedPosition(BaseModel):
    """A position inside a department, and who it reports to (the org chart)."""

    ref: str
    title: str
    department: str
    reports_to: str | None = None
    rationale: str


class ProposedKeyResult(BaseModel):
    """One measurable key result of an objective. The ref lets a KPI point at it."""

    ref: str
    description: str


class ProposedObjective(BaseModel):
    """An objective with its key results; no department means a company-wide objective."""

    ref: str
    title: str
    department: str | None = None
    key_results: list[ProposedKeyResult]
    rationale: str


class ProposedKPI(BaseModel):
    """A measurable indicator for one department, with its share of that department's score."""

    name: str
    department: str
    key_result: str | None = None
    weight: float
    target_value: float | None = None
    unit: str | None = None
    lower_is_better: bool = False
    rationale: str


class ProposedCleanup(BaseModel):
    """A fix for something the company already has: rename it, or flag it for a human."""

    target: str
    action: Literal["rename", "review"]
    new_name: str | None = None
    note: str


class BlueprintAnswer(BaseModel):
    """Claude's whole answer for one organization."""

    departments: list[ProposedDepartment]
    positions: list[ProposedPosition]
    objectives: list[ProposedObjective]
    kpis: list[ProposedKPI]
    cleanups: list[ProposedCleanup]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class BlueprintItemResponse(BaseModel):
    """One proposed item as the review screen shows it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_id: uuid.UUID
    kind: str
    ref: str | None
    sort_order: int
    title: str
    rationale: str
    department_id: uuid.UUID | None
    position_id: uuid.UUID | None
    reports_to_position_id: uuid.UUID | None
    department_ref: str | None
    reports_to_ref: str | None
    objective_ref: str | None
    key_result_ref: str | None
    kpi_weight: decimal.Decimal | None
    kpi_target_value: decimal.Decimal | None
    kpi_unit: str | None
    kpi_is_inverse: bool | None
    status: str
    reviewed_title: str | None
    reviewed_at: datetime | None
    created_entity_id: uuid.UUID | None
    created_at: datetime


class BlueprintEditRequest(BaseModel):
    """HR's corrected wording for one item. Only the wording can be edited."""

    title: str = Field(min_length=1, max_length=300)


class AcceptAllSkipped(BaseModel):
    """One item that 'accept all' could not apply, and why."""

    id: uuid.UUID
    title: str
    reason: str


class AcceptAllResponse(BaseModel):
    """What 'accept all' did."""

    accepted: int
    skipped: list[AcceptAllSkipped]


class GenerateResponse(BaseModel):
    """Answer to 'generate my blueprint': queued, or already waiting for review."""

    status: Literal["queued", "already_pending"]
