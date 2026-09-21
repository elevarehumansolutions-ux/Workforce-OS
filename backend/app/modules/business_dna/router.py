"""FastAPI routes for the Business DNA module.

Exposes GET|PUT /business-dna (upsert) and the core-value CRUD set. Reads
are open to any authenticated org member; mutations are gated to HR
Administrator. capital_investment_amount is additionally field-restricted
to hr_administrator/business_executive on reads, not gated by role at the
endpoint level — see 08_DECISIONS.md 2026-09-21.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_membership, get_db, require_org_role
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.repository import OrganizationRepository

from .models import BusinessDNA, BusinessDNACoreValue
from .schemas import (
    BusinessDNACoreValueCreateRequest,
    BusinessDNACoreValueResponse,
    BusinessDNACoreValueUpdateRequest,
    BusinessDNAResponse,
    BusinessDNAUpsertRequest,
)
from .service import BusinessDNACoreValueService, BusinessDNAService

router = APIRouter()

_WRITE_ROLES = ("hr_administrator",)
_CAPITAL_INVESTMENT_VISIBLE_ROLES = {"hr_administrator", "business_executive"}


def _to_response(
    business_dna: BusinessDNA,
    core_values: list[BusinessDNACoreValue],
    organization_name: str | None,
    caller_role: str,
) -> BusinessDNAResponse:
    """Build the response schema by hand, field by field.

    Not ``BusinessDNAResponse.model_validate(business_dna)``: this schema
    has two fields that aren't plain columns on ``business_dna`` —
    ``core_values`` is a relationship and ``organization_name`` isn't a
    column at all (08_DECISIONS.md 2026-09-21). Letting Pydantic's
    ``from_attributes`` mode touch either of those on an unloaded async
    relationship would trigger a lazy-load and crash with
    ``MissingGreenlet`` — the exact bug class M4 already hit once. Both are
    supplied as already-fetched values instead, never via attribute access
    on the ORM relationship.

    ``capital_investment_amount`` is nulled out here for any role outside
    the restricted set — the one piece of role-aware logic in this schema
    that no ``model_validate`` call could express on its own.
    """
    return BusinessDNAResponse(
        id=business_dna.id,
        organization_id=business_dna.organization_id,
        organization_name=organization_name,
        industry=business_dna.industry,
        products_services_description=business_dna.products_services_description,
        vision=business_dna.vision,
        mission=business_dna.mission,
        business_model=business_dna.business_model,
        performance_philosophy=business_dna.performance_philosophy,
        workforce_rules=business_dna.workforce_rules,
        revenue_drivers=business_dna.revenue_drivers,
        operational_drivers=business_dna.operational_drivers,
        customer_value_drivers=business_dna.customer_value_drivers,
        capital_investment_amount=(
            business_dna.capital_investment_amount
            if caller_role in _CAPITAL_INVESTMENT_VISIBLE_ROLES
            else None
        ),
        core_values=[BusinessDNACoreValueResponse.model_validate(v) for v in core_values],
        created_at=business_dna.created_at,
        updated_at=business_dna.updated_at,
    )


@router.get("/business-dna", status_code=200)
async def get_business_dna(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> BusinessDNAResponse:
    """Get the caller's organization's Business DNA profile.

    Open to any authenticated member of the organization.
    ``capital_investment_amount`` is only populated for
    hr_administrator/business_executive callers; every other role sees it
    as null.

    Args:
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping and the
            capital_investment_amount field restriction.

    Returns:
        The organization's Business DNA profile, including its core values.

    Raises:
        BusinessDNANotFoundException: If the org hasn't filled it in yet
            (translates to a 404 response).
    """
    service = BusinessDNAService(db)
    core_value_service = BusinessDNACoreValueService(db)
    organization_repo = OrganizationRepository(db)

    business_dna = await service.get_business_dna(caller.organization_id)
    core_values = await core_value_service.list_core_values(caller.organization_id)
    organization = await organization_repo.get_organization_by_id(caller.organization_id)

    return _to_response(business_dna, core_values, organization.name, caller.role)


@router.put("/business-dna", status_code=200)
async def upsert_business_dna(
    data: BusinessDNAUpsertRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> BusinessDNAResponse:
    """Create or update the caller's organization's Business DNA profile.

    A single upsert endpoint — the onboarding wizard can call this whether
    it's the first save or a later edit, without needing to know which.
    Requires the HR Administrator role.

    Args:
        data: Business DNA fields to create or update, plus the optional
            ``organization_name``, written through to ``organizations.name``
            in the same transaction (08_DECISIONS.md 2026-09-21).
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The created or updated Business DNA profile.
    """
    service = BusinessDNAService(db)
    core_value_service = BusinessDNACoreValueService(db)
    organization_repo = OrganizationRepository(db)

    business_dna = await service.upsert_business_dna(
        caller.organization_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()

    core_values = await core_value_service.list_core_values(caller.organization_id)
    organization = await organization_repo.get_organization_by_id(caller.organization_id)

    return _to_response(business_dna, core_values, organization.name, caller.role)


# ---------------------------------------------------------------------------
# Core values
# ---------------------------------------------------------------------------

@router.post("/business-dna/core-values", status_code=200)
async def create_core_value(
    data: BusinessDNACoreValueCreateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> BusinessDNACoreValueResponse:
    """Add a core value to the caller's organization's Business DNA profile.

    Requires the HR Administrator role.

    Args:
        data: Core value fields to create.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The newly created core value.

    Raises:
        BusinessDNANotFoundException: If the org hasn't created a Business
            DNA profile yet (translates to a 404 response) — a core value
            can't exist without a parent profile to attach to.
    """
    service = BusinessDNACoreValueService(db)
    core_value = await service.create_core_value(
        caller.organization_id, caller.user_id, data.model_dump()
    )
    await db.commit()
    return BusinessDNACoreValueResponse.model_validate(core_value)


@router.get("/business-dna/core-values", status_code=200)
async def list_core_values(
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(get_current_membership),
) -> list[BusinessDNACoreValueResponse]:
    """List every core value for the caller's organization's Business DNA profile.

    Open to any authenticated member of the organization.

    Args:
        db: Database session dependency.
        caller: Caller's membership, used for organization scoping.

    Returns:
        The matching core values, or an empty list if no profile exists yet.
    """
    service = BusinessDNACoreValueService(db)
    core_values = await service.list_core_values(caller.organization_id)
    return [BusinessDNACoreValueResponse.model_validate(v) for v in core_values]


@router.patch("/business-dna/core-values/{core_value_id}", status_code=200)
async def update_core_value(
    core_value_id: uuid.UUID,
    data: BusinessDNACoreValueUpdateRequest,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> BusinessDNACoreValueResponse:
    """Apply a partial update to a core value.

    Requires the HR Administrator role.

    Args:
        core_value_id: Id of the core value to update.
        data: Fields to update.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Returns:
        The updated core value.

    Raises:
        BusinessDNACoreValueNotFoundException: If no core value with that
            id exists in the caller's org (translates to a 404 response).
    """
    service = BusinessDNACoreValueService(db)
    core_value = await service.update_core_value(
        core_value_id, caller.user_id, data.model_dump(exclude_unset=True)
    )
    await db.commit()
    return BusinessDNACoreValueResponse.model_validate(core_value)


@router.delete("/business-dna/core-values/{core_value_id}", status_code=204)
async def delete_core_value(
    core_value_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: Membership = Depends(require_org_role(*_WRITE_ROLES)),
) -> None:
    """Hard-delete a core value.

    Returns 204 with no body, unlike the org-structure module's soft
    deletes (which return the deleted resource) — there's no updated
    resource state to hand back for a genuine hard delete.

    Requires the HR Administrator role.

    Args:
        core_value_id: Id of the core value to delete.
        db: Database session dependency.
        caller: Caller's membership; must be an HR Administrator.

    Raises:
        BusinessDNACoreValueNotFoundException: If no core value with that
            id exists in the caller's org (translates to a 404 response).
    """
    service = BusinessDNACoreValueService(db)
    await service.delete_core_value(core_value_id, caller.user_id)
    await db.commit()
