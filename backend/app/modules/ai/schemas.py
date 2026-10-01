"""Pydantic schemas for the AI suggestions module."""

import uuid
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.modules.organization.enums import CriticalityType, RiskLevel

from .enums import SuggestionType

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AISuggestionCreateRequest(BaseModel):
    """A candidate suggestion to persist, as produced by the generation code.

    Internal input (validated LLM output), not an HTTP body.
    ``organization_id`` is deliberately absent — supplied by the caller
    from the tenant context, never from the candidate itself. Enforces the
    same type-to-target pairing as the database CHECK constraint so a
    malformed candidate is rejected here instead of raising an
    ``IntegrityError`` mid-batch, which would abort the whole transaction.
    Enum-typed fields are dumped as plain values (``use_enum_values``) so
    ``model_dump()`` can go straight to the repository.
    """

    model_config = ConfigDict(use_enum_values=True)

    suggestion_type: SuggestionType
    position_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    suggested_department_name: NonBlankStr | None = None
    suggested_criticality_type: CriticalityType | None = None
    suggested_risk_level: RiskLevel | None = None
    suggested_revenue_allocation_percentage: Decimal | None = None
    kpi_id: uuid.UUID | None = None
    suggested_weight: Decimal | None = None
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _target_matches_type(self) -> "AISuggestionCreateRequest":
        """Require the target this suggestion type points at, and what it must carry.

        A ``critical_position`` suggestion must also carry both
        ``suggested_criticality_type`` and ``suggested_risk_level``, a
        ``revenue_allocation`` one its percentage (08_DECISIONS.md
        2026-09-24), and a ``kpi_weight`` one its weight (08_DECISIONS.md
        2026-09-30): approving one without them would apply nothing
        meaningful to the real row.
        """
        required = {
            SuggestionType.CRITICAL_POSITION.value: self.position_id,
            SuggestionType.REVENUE_ALLOCATION.value: self.department_id,
            SuggestionType.MISSING_DEPARTMENT.value: self.suggested_department_name,
            SuggestionType.KPI_WEIGHT.value: self.kpi_id,
        }[self.suggestion_type]
        if required is None:
            raise ValueError(
                f"{self.suggestion_type} suggestions require their target field to be set"
            )

        missing = []
        if self.suggestion_type == SuggestionType.CRITICAL_POSITION.value:
            if self.suggested_criticality_type is None:
                missing.append("suggested_criticality_type")
            if self.suggested_risk_level is None:
                missing.append("suggested_risk_level")
        elif self.suggestion_type == SuggestionType.REVENUE_ALLOCATION.value:
            if self.suggested_revenue_allocation_percentage is None:
                missing.append("suggested_revenue_allocation_percentage")
        elif self.suggestion_type == SuggestionType.KPI_WEIGHT.value:
            if self.suggested_weight is None:
                missing.append("suggested_weight")
        if missing:
            raise ValueError(
                f"{self.suggestion_type} suggestions require: {', '.join(missing)}"
            )
        return self


class AISuggestionResponse(BaseModel):
    """API representation of an AI suggestion."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    suggestion_type: str
    position_id: uuid.UUID | None
    department_id: uuid.UUID | None
    suggested_department_name: str | None
    suggested_criticality_type: str | None
    suggested_risk_level: str | None
    suggested_revenue_allocation_percentage: Decimal | None
    kpi_id: uuid.UUID | None
    suggested_weight: Decimal | None
    rationale: str
    status: str
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    reviewed_criticality_type: str | None
    reviewed_risk_level: str | None
    reviewed_revenue_allocation_percentage: Decimal | None
    reviewed_department_name: str | None
    reviewed_weight: Decimal | None
    created_at: datetime
    updated_at: datetime


class AISuggestionEditRequest(BaseModel):
    """What a reviewer can change on a suggestion; anything left out keeps the AI's value."""

    model_config = ConfigDict(use_enum_values=True)

    criticality_type: CriticalityType | None = None
    risk_level: RiskLevel | None = None
    revenue_allocation_percentage: Decimal | None = None
    department_name: NonBlankStr | None = None
    weight: Decimal | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "AISuggestionEditRequest":
        """Reject an edit that changes nothing at all."""
        if all(
            value is None
            for value in (
                self.criticality_type,
                self.risk_level,
                self.revenue_allocation_percentage,
                self.department_name,
                self.weight,
            )
        ):
            raise ValueError("an edit must change at least one field")
        return self


@dataclass
class ResolvedHandles:
    """The real ids Claude's answer pointed at, and the handles that pointed at nothing."""

    ids: list[uuid.UUID]
    dropped: list[str]


class CriticalPositionPick(BaseModel):
    """One position Claude thinks is critical, and why."""

    handle: str
    criticality_type: CriticalityType
    risk_level: RiskLevel
    rationale: NonBlankStr


class CriticalPositionAnswer(BaseModel):
    """Claude's full answer for a critical-position run; an empty list is valid."""

    picks: list[CriticalPositionPick]


class RevenueAllocationPick(BaseModel):
    """One critical department Claude proposes a revenue share for, and why.

    No bound is enforced on the percentage (08_DECISIONS.md 2026-09-24):
    department allocations may legitimately sum over 100%, each an
    independent expected-return target on the capital investment, not a
    slice of a fixed budget.
    """

    handle: str
    revenue_allocation_percentage: Decimal
    rationale: NonBlankStr


class RevenueAllocationAnswer(BaseModel):
    """Claude's full answer for a revenue-allocation run; an empty list is valid."""

    picks: list[RevenueAllocationPick]


class MissingDepartmentPick(BaseModel):
    """One department Claude thinks the org is missing, and why.

    No handle: unlike the other two types, there's nothing real to point
    at yet — the whole point of this suggestion type is naming something
    that doesn't exist. That's also why there's no grounding-by-handle step
    for it: the per-run cap (``select_missing_department_picks``) and the
    existing name-based idempotency (the pending-duplicate index, the
    quarterly rejection suppression) are what keep this type honest instead.
    """

    department_name: NonBlankStr
    rationale: NonBlankStr


class MissingDepartmentAnswer(BaseModel):
    """Claude's full answer for a missing-department run; an empty list is valid."""

    picks: list[MissingDepartmentPick]


class KPIWeightPick(BaseModel):
    """One existing KPI Claude proposes a weight for, and why.

    Unlike every other pick type, these don't stand alone — the whole
    point is that the picks returned for one department/location group
    sum to 100 together (08_DECISIONS.md 2026-09-30). Checked at
    selection time, not here on the individual pick.
    """

    handle: str
    suggested_weight: Decimal
    rationale: NonBlankStr


class KPIWeightAnswer(BaseModel):
    """Claude's full answer for one KPI-weight group; an empty list is valid."""

    picks: list[KPIWeightPick]


class AIUsageLogResponse(BaseModel):
    """API representation of one LLM usage-log row, returned by GET /ai-usage."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    purpose: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cache_write_tokens: int
    cache_read_tokens: int
    estimated_cost_usd: Decimal | None
    created_at: datetime

