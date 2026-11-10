"""Pydantic schemas for the blueprint module.

Two groups: what Claude must answer with (``Proposed*``, ``BlueprintAnswer``)
and what the API sends and receives.
"""

import decimal
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.organization.enums import CriticalityType, RiskLevel


# ---------------------------------------------------------------------------
# What Claude answers with
# ---------------------------------------------------------------------------
# Claude never sees database ids. New things get labels it invents (D1, P1,
# O1); things the company already has are shown to it as ED1..., EP1... and it
# must point at those labels, so nothing it says can reach a real row we did
# not show it.


class ProposedDepartment(BaseModel):
    """A department the company should have.

    ``is_critical`` and ``revenue_allocation_pct`` are the AI's call, not the user's:
    the capital investment is SPLIT between the critical departments, so their shares
    (0 to 100 each) should add up to 100 (the code rescales them to exactly 100).
    ``profit_margin_pct`` is a typical profit margin (0 to 100) for that kind of
    department, an estimate.
    """

    ref: str
    name: str
    is_critical: bool = False
    revenue_allocation_pct: float | None = None
    profit_margin_pct: float | None = None
    rationale: str


class ProposedPosition(BaseModel):
    """A position inside a department, and who it reports to (the org chart).

    A critical position needs both its kind of criticality and its risk level.
    """

    ref: str
    title: str
    department: str
    reports_to: str | None = None
    is_critical: bool = False
    criticality_type: CriticalityType | None = None
    risk_level: RiskLevel | None = None
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


class ProposedFold(BaseModel):
    """A department or role the plan leaves out, because another one covers its work.

    Example: kind "department", name "Talent Sourcing", covered_by "D3" (Recruitment).
    A combined role is not a fold: it is a normal position with a combined title,
    and the roles it replaces are listed here as folds into it.
    """

    kind: Literal["department", "position"]
    name: str
    covered_by: str
    reason: str


class BlueprintAnswer(BaseModel):
    """Claude's whole answer for one organization."""

    departments: list[ProposedDepartment]
    positions: list[ProposedPosition]
    objectives: list[ProposedObjective]
    kpis: list[ProposedKPI]
    cleanups: list[ProposedCleanup]
    # Optional so an answer without any folds is still valid.
    folded: list[ProposedFold] = []


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
    folded_into_ref: str | None
    key_result_ref: str | None
    is_critical: bool | None
    revenue_allocation_pct: decimal.Decimal | None
    profit_margin_pct: decimal.Decimal | None
    criticality_type: str | None
    risk_level: str | None
    kpi_weight: decimal.Decimal | None
    kpi_target_value: decimal.Decimal | None
    kpi_unit: str | None
    kpi_is_inverse: bool | None
    status: str
    reviewed_title: str | None
    reviewed_at: datetime | None
    created_entity_id: uuid.UUID | None
    created_at: datetime


class BlueprintMergeRequest(BaseModel):
    """What the item should be merged into: give exactly ONE of the two.

    ``target_id`` is another suggested item of the plan; ``existing_id`` is a real
    department or position the company already has.
    """

    target_id: uuid.UUID | None = None
    existing_id: uuid.UUID | None = None


class BlueprintEditRequest(BaseModel):
    """HR's corrections to one item before it is added: the wording, and a few details.

    ``title`` is always sent. The detail fields are optional and only apply to the kinds named:
    a KPI's target, unit and direction; a department's share of the capital and profit margin.
    A field left out keeps the proposal's value; for the nullable ones an explicit ``null``
    clears it. A detail that does not belong to the item's kind is a 422.
    """

    title: str = Field(min_length=1, max_length=300)
    # KPI
    kpi_target_value: decimal.Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    kpi_unit: str | None = Field(default=None, max_length=40)
    kpi_is_inverse: bool | None = None
    # Department
    revenue_allocation_pct: decimal.Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    profit_margin_pct: decimal.Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


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
