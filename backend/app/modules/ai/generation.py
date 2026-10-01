"""Generation of AI suggestions: gather context, ask Claude, ground the answer."""

import logging
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import OrganizationNotFoundException
from app.core.fiscal import get_fiscal_quarter_start
from app.modules.business_dna.repository import BusinessDNARepository
from app.modules.kpis.repository import KPIRepository
from app.modules.okrs.repository import OKRRepository
from app.modules.organization.repository import DepartmentRepository, PositionRepository
from app.modules.tenancy_identity.repository import OrganizationRepository

from .enums import AIUsagePurpose, ModelTier, SuggestionType
from .grounding import make_handles, normalize_handle, resolve_handles
from .llm import generate_structured
from .prompts import (
    BusinessContext,
    PromptDepartment,
    PromptDepartmentHandle,
    PromptKPIHandle,
    PromptPosition,
    build_critical_position_prompt,
    build_kpi_weight_prompt,
    build_missing_department_prompt,
    build_revenue_allocation_prompt,
    critical_position_system_prompt,
    kpi_weight_system_prompt,
    missing_department_system_prompt,
    revenue_allocation_system_prompt,
)
from .repository import AISuggestionRepository
from .schemas import (
    AISuggestionCreateRequest,
    AISuggestionResponse,
    CriticalPositionAnswer,
    CriticalPositionPick,
    KPIWeightAnswer,
    KPIWeightPick,
    MissingDepartmentAnswer,
    MissingDepartmentPick,
    RevenueAllocationAnswer,
    RevenueAllocationPick,
)
from .service import AISuggestionService

logger = logging.getLogger(__name__)

# How far a group's resolved total may drift from 100 and still be used —
# not zero, since Claude's arithmetic can round a cent off; not loose
# either, since this is what tells a usable proposal apart from a broken
# one worth dropping outright (see select_kpi_weight_picks).
_KPI_WEIGHT_TOTAL_TOLERANCE = Decimal("0.5")


@dataclass(frozen=True)
class CriticalPositionContext:
    """Everything one critical-position run needs, gathered up front."""

    business: BusinessContext
    departments: list[PromptDepartment]
    handles: dict[str, uuid.UUID]
    department_of: dict[uuid.UUID, uuid.UUID]


async def gather_critical_position_context(
    db: AsyncSession, organization_id: uuid.UUID
) -> CriticalPositionContext | None:
    """Collect prompt inputs, or None if there is nothing to ask Claude about."""
    rows = await PositionRepository(db).list_candidate_positions_for_criticality(organization_id)
    if not rows:
        return None
    
    handles = make_handles([position.id for position, _ in rows], "P")
    grouped: dict[uuid.UUID, tuple[str, list[PromptPosition]]] = {}
    department_of: dict[uuid.UUID, uuid.UUID] = {}

    # Handles keep insertion order, so zip pairs P1 with the first row, P2 with the second...
    for handle, (position, department) in zip(handles, rows):
        _, positions = grouped.setdefault(department.id, (department.name, []))
        positions.append(PromptPosition(handle, position.title))
        department_of[position.id] = department.id
    
    dna = await BusinessDNARepository(db).get_business_dna_by_organization_id(organization_id)
    business = (
        BusinessContext(
            industry=dna.industry,
            products_services=dna.products_services_description,
            revenue_drivers=dna.revenue_drivers,
            operational_drivers=dna.operational_drivers,
            customer_value_drivers=dna.customer_value_drivers,
        )
        if dna
        else BusinessContext()
    )

    return CriticalPositionContext(
        business=business,
        departments=[PromptDepartment(name, positions) for name, positions in grouped.values()],
        handles=handles,
        department_of=department_of,
    )

def select_critical_picks(
    picks: Sequence[CriticalPositionPick], context: CriticalPositionContext
) -> list[tuple[uuid.UUID, CriticalPositionPick]]:
    """Ground Claude's picks and apply the per-department cap.

    Returns ``(position_id, pick)`` pairs: real positions only, each at most
    once, and no more than the configured number per department.

    Raises:
        LLMOutputError: Most of the picks point at positions that don't exist.
    """
    resolved = resolve_handles([pick.handle for pick in picks], context.handles)

    allowed = set(resolved.ids)
    limit = settings.ai_max_critical_positions_per_department_per_run

    chosen: list[tuple[uuid.UUID, CriticalPositionPick]] = []
    taken: set[uuid.UUID] = set()
    per_department: Counter[uuid.UUID] = Counter()

    for pick in picks:
        position_id = context.handles.get(normalize_handle(pick.handle))
        if position_id not in allowed or position_id in taken:
            continue
        dept_id = context.department_of[position_id]
        if per_department[dept_id] >= limit:
            continue
        
        per_department[dept_id] += 1
        taken.add(position_id)
        chosen.append((position_id, pick))
    return chosen

async def generate_critical_position_suggestions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[AISuggestionResponse]:
    """Run one critical-position generation for an organization.

    Never commits: the caller (the Celery task) owns the transaction.

    Returns:
        The suggestions newly created by this run. Candidates skipped as
        duplicates or recently rejected are not included.
    """
    context = await gather_critical_position_context(db, organization_id)
    if context is None:
        return []
    
    answer = await generate_structured(
        db,
        organization_id=organization_id,
        purpose=AIUsagePurpose.AI_SUGGESTION_GENERATION,
        tier=ModelTier.FAST,
        system=critical_position_system_prompt(),
        prompt=build_critical_position_prompt(context.business, context.departments),
        output_type=CriticalPositionAnswer,
    )

    service = AISuggestionService(db)
    created: list[AISuggestionResponse] = []
    for position_id, pick in select_critical_picks(answer.picks, context):
        suggestion = await service.create_suggestion_if_eligible(
            organization_id,
            AISuggestionCreateRequest(
                suggestion_type=SuggestionType.CRITICAL_POSITION,
                position_id=position_id,
                suggested_criticality_type=pick.criticality_type,
                suggested_risk_level=pick.risk_level,
                rationale=pick.rationale,
            ),
        )
        if suggestion is not None:
            created.append(suggestion)
    return created


@dataclass(frozen=True)
class RevenueAllocationContext:
    """Everything one revenue-allocation run needs, gathered up front."""

    business: BusinessContext
    departments: list[PromptDepartmentHandle]
    handles: dict[str, uuid.UUID]


async def gather_revenue_allocation_context(
    db: AsyncSession, organization_id: uuid.UUID
) -> RevenueAllocationContext | None:
    """Collect prompt inputs, or None if there is no critical department to ask Claude about."""
    departments = await DepartmentRepository(db).list_candidate_departments_for_revenue_allocation(
        organization_id
    )
    if not departments:
        return None

    handles = make_handles([department.id for department in departments], "D")
    # handles keeps insertion order, so zip pairs D1 with the first department, D2 with the second...
    prompt_departments = [
        PromptDepartmentHandle(handle, department.name)
        for handle, department in zip(handles, departments)
    ]

    dna = await BusinessDNARepository(db).get_business_dna_by_organization_id(organization_id)
    business = (
        BusinessContext(
            industry=dna.industry,
            products_services=dna.products_services_description,
            revenue_drivers=dna.revenue_drivers,
            operational_drivers=dna.operational_drivers,
            customer_value_drivers=dna.customer_value_drivers,
            capital_investment_amount=dna.capital_investment_amount,
        )
        if dna
        else BusinessContext()
    )

    return RevenueAllocationContext(business=business, departments=prompt_departments, handles=handles)


def select_revenue_allocation_picks(
    picks: Sequence[RevenueAllocationPick], context: RevenueAllocationContext
) -> list[tuple[uuid.UUID, RevenueAllocationPick]]:
    """Ground Claude's picks: real departments only, each at most once.

    No per-department cap here — each pick already targets a distinct
    critical department, and critical departments are HR-created, so
    there's no risk of the volume growing unbounded the way an invented
    department name could (that's what the ``missing_department`` caps are
    for). A department picked twice keeps its first-listed percentage.

    Raises:
        LLMOutputError: Most of the picks point at departments that don't exist.
    """
    resolved = resolve_handles([pick.handle for pick in picks], context.handles)
    allowed = set(resolved.ids)

    chosen: list[tuple[uuid.UUID, RevenueAllocationPick]] = []
    taken: set[uuid.UUID] = set()
    for pick in picks:
        department_id = context.handles.get(normalize_handle(pick.handle))
        if department_id not in allowed or department_id in taken:
            continue
        taken.add(department_id)
        chosen.append((department_id, pick))
    return chosen


async def generate_revenue_allocation_suggestions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[AISuggestionResponse]:
    """Run one revenue-allocation generation for an organization.

    Never commits: the caller (the Celery task) owns the transaction.

    Returns:
        The suggestions newly created by this run. Candidates skipped as
        duplicates or recently rejected are not included.
    """
    context = await gather_revenue_allocation_context(db, organization_id)
    if context is None:
        return []

    answer = await generate_structured(
        db,
        organization_id=organization_id,
        purpose=AIUsagePurpose.AI_SUGGESTION_GENERATION,
        tier=ModelTier.STRONG,
        system=revenue_allocation_system_prompt(),
        prompt=build_revenue_allocation_prompt(context.business, context.departments),
        output_type=RevenueAllocationAnswer,
    )

    service = AISuggestionService(db)
    created: list[AISuggestionResponse] = []
    for department_id, pick in select_revenue_allocation_picks(answer.picks, context):
        suggestion = await service.create_suggestion_if_eligible(
            organization_id,
            AISuggestionCreateRequest(
                suggestion_type=SuggestionType.REVENUE_ALLOCATION,
                department_id=department_id,
                suggested_revenue_allocation_percentage=pick.revenue_allocation_percentage,
                rationale=pick.rationale,
            ),
        )
        if suggestion is not None:
            created.append(suggestion)
    return created


@dataclass(frozen=True)
class MissingDepartmentContext:
    """Everything one missing-department run needs, gathered up front."""

    business: BusinessContext
    existing_department_names: list[str]
    already_rejected_department_names: list[str]
    objective_titles: list[str]


async def gather_missing_department_context(
    db: AsyncSession, organization_id: uuid.UUID
) -> MissingDepartmentContext:
    """Collect prompt inputs for a missing-department run.

    Unlike the other two types, there's no "nothing to ask about" case to
    return None for here — an org with zero departments and zero OKRs is
    exactly the situation this suggestion type exists for, not a reason to
    skip it.

    Raises:
        OrganizationNotFoundException: If the organization isn't visible
            under the current tenant context.
    """
    organization = await OrganizationRepository(db).get_organization_by_id(organization_id)
    if organization is None:
        raise OrganizationNotFoundException()
    fiscal_quarter_start = get_fiscal_quarter_start(
        organization.fiscal_year_start_month, datetime.now(UTC)
    )

    existing_names = await DepartmentRepository(db).list_active_department_names(organization_id)
    rejected_names = await AISuggestionRepository(db).list_recent_rejected_department_names(
        organization_id, fiscal_quarter_start
    )
    objective_titles = await OKRRepository(db).list_active_objective_titles(organization_id)

    dna = await BusinessDNARepository(db).get_business_dna_by_organization_id(organization_id)
    business = (
        BusinessContext(
            industry=dna.industry,
            products_services=dna.products_services_description,
            revenue_drivers=dna.revenue_drivers,
            operational_drivers=dna.operational_drivers,
            customer_value_drivers=dna.customer_value_drivers,
        )
        if dna
        else BusinessContext()
    )

    return MissingDepartmentContext(
        business=business,
        existing_department_names=existing_names,
        already_rejected_department_names=rejected_names,
        objective_titles=objective_titles,
    )


def select_missing_department_picks(
    picks: Sequence[MissingDepartmentPick],
) -> list[MissingDepartmentPick]:
    """Apply the per-run cap; keep Claude's own order.

    Nothing to ground here — a name is the whole point of this type, not
    something to validate against a real row. Exact duplicates within one
    batch are left for the database's own normalized-name uniqueness to
    catch (``create_pending_suggestion``'s ``ON CONFLICT DO NOTHING``): a
    Python-side re-check would either re-implement that normalization (a
    real drift risk — see ``core/text.py``) or under-match it.
    """
    limit = settings.ai_max_missing_departments_per_run
    return list(picks[:limit])


async def generate_missing_department_suggestions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[AISuggestionResponse]:
    """Run one missing-department generation for an organization.

    Never commits: the caller (the Celery task) owns the transaction.

    Returns:
        The suggestions newly created by this run. Candidates skipped as
        duplicates or recently rejected are not included.
    """
    context = await gather_missing_department_context(db, organization_id)

    answer = await generate_structured(
        db,
        organization_id=organization_id,
        purpose=AIUsagePurpose.AI_SUGGESTION_GENERATION,
        tier=ModelTier.STRONG,
        system=missing_department_system_prompt(),
        prompt=build_missing_department_prompt(
            context.business,
            context.existing_department_names,
            context.already_rejected_department_names,
            context.objective_titles,
        ),
        output_type=MissingDepartmentAnswer,
    )

    service = AISuggestionService(db)
    created: list[AISuggestionResponse] = []
    for pick in select_missing_department_picks(answer.picks):
        suggestion = await service.create_suggestion_if_eligible(
            organization_id,
            AISuggestionCreateRequest(
                suggestion_type=SuggestionType.MISSING_DEPARTMENT,
                suggested_department_name=pick.department_name,
                rationale=pick.rationale,
            ),
        )
        if suggestion is not None:
            created.append(suggestion)
    return created


@dataclass(frozen=True)
class KPIWeightGroupContext:
    """Everything one KPI-weight group's run needs, gathered up front."""

    department_id: uuid.UUID
    department_name: str
    location_id: uuid.UUID | None
    kpis: list[PromptKPIHandle]
    handles: dict[str, uuid.UUID]


async def gather_kpi_weight_contexts(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[KPIWeightGroupContext]:
    """One context per department/location group worth proposing a weight split for.

    Unlike the other three chains, there is no single "the context" —
    each candidate group's KPI names only mean something within that one
    group, so each needs its own handle set (K1, K2, ... restarting per
    group, never shared across groups).
    """
    kpi_repo = KPIRepository(db)
    groups = await kpi_repo.list_candidate_kpi_groups_for_weight_suggestion(organization_id)

    contexts: list[KPIWeightGroupContext] = []
    for department_id, department_name, location_id in groups:
        kpis = await kpi_repo.list_kpis_in_group(department_id, location_id)
        handles = make_handles([kpi.id for kpi in kpis], "K")
        prompt_kpis = [
            PromptKPIHandle(handle, kpi.name) for handle, kpi in zip(handles, kpis)
        ]
        contexts.append(
            KPIWeightGroupContext(
                department_id=department_id,
                department_name=department_name,
                location_id=location_id,
                kpis=prompt_kpis,
                handles=handles,
            )
        )
    return contexts


def select_kpi_weight_picks(
    picks: Sequence[KPIWeightPick], context: KPIWeightGroupContext
) -> list[tuple[uuid.UUID, KPIWeightPick]]:
    """Ground Claude's picks for one group: real KPIs only, each at most once.

    Unlike every other pick type, an individual pick isn't meaningful on
    its own — the whole group's resolved weights have to sum to (close
    to) 100, since this is a full re-split of the group, not independent
    scores. A group whose resolved total drifts too far from 100 is
    dropped **entirely**, not partially applied or auto-corrected: a
    lopsided proposal is worse than none, since it would otherwise reach
    review one KPI at a time with no way for the reviewer to see the
    others went wrong too (08_DECISIONS.md 2026-09-30).

    Raises:
        LLMOutputError: Most of the picks point at KPIs that don't exist.
    """
    resolved = resolve_handles([pick.handle for pick in picks], context.handles)
    allowed = set(resolved.ids)

    chosen: list[tuple[uuid.UUID, KPIWeightPick]] = []
    taken: set[uuid.UUID] = set()
    for pick in picks:
        kpi_id = context.handles.get(normalize_handle(pick.handle))
        if kpi_id not in allowed or kpi_id in taken:
            continue
        taken.add(kpi_id)
        chosen.append((kpi_id, pick))

    total = sum((pick.suggested_weight for _, pick in chosen), Decimal("0"))
    if not chosen or abs(total - 100) > _KPI_WEIGHT_TOTAL_TOLERANCE:
        logger.warning(
            "Dropping kpi_weight picks for department %s (location %s): "
            "resolved total %s, not within tolerance of 100",
            context.department_id, context.location_id, total,
        )
        return []
    return chosen


async def generate_kpi_weight_suggestions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[AISuggestionResponse]:
    """Run one kpi-weight generation per candidate group for an organization.

    Never commits: the caller (the Celery task) owns the transaction.
    One Claude call per candidate group — unlike the other three chains,
    a KPI's weight only means something within its own department/
    location group, so groups can't share a single call the way
    departments/positions do.

    Returns:
        The suggestions newly created by this run, across every
        candidate group. Candidates skipped as duplicates, recently
        rejected, or part of a dropped (off-total) group are not
        included.
    """
    contexts = await gather_kpi_weight_contexts(db, organization_id)
    if not contexts:
        return []

    dna = await BusinessDNARepository(db).get_business_dna_by_organization_id(organization_id)
    business = (
        BusinessContext(
            industry=dna.industry,
            products_services=dna.products_services_description,
            revenue_drivers=dna.revenue_drivers,
            operational_drivers=dna.operational_drivers,
            customer_value_drivers=dna.customer_value_drivers,
            capital_investment_amount=dna.capital_investment_amount,
        )
        if dna
        else BusinessContext()
    )

    service = AISuggestionService(db)
    created: list[AISuggestionResponse] = []
    for context in contexts:
        answer = await generate_structured(
            db,
            organization_id=organization_id,
            purpose=AIUsagePurpose.AI_SUGGESTION_GENERATION,
            tier=ModelTier.STRONG,
            system=kpi_weight_system_prompt(),
            prompt=build_kpi_weight_prompt(business, context.department_name, context.kpis),
            output_type=KPIWeightAnswer,
        )
        for kpi_id, pick in select_kpi_weight_picks(answer.picks, context):
            suggestion = await service.create_suggestion_if_eligible(
                organization_id,
                AISuggestionCreateRequest(
                    suggestion_type=SuggestionType.KPI_WEIGHT,
                    kpi_id=kpi_id,
                    suggested_weight=pick.suggested_weight,
                    rationale=pick.rationale,
                ),
            )
            if suggestion is not None:
                created.append(suggestion)
    return created
