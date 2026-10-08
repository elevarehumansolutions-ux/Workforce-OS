"""Data-access layer for the Business DNA module.

Provides CRUD and lookup operations for an organization's Business DNA
profile and its core values. Every repository operates within the caller's
RLS-scoped session and only flushes (never commits) — commits are the
service layer's responsibility. Not-found handling lives in the service
layer, not here: callers fetch first (``get_*_by_id``) and pass the
instance itself into ``update``/``delete``, matching the org structure
module's convention.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BusinessDNA, BusinessDNACoreValue


class BusinessDNARepository:
    """Handles persistence for an organization's Business DNA profile."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_business_dna(self, business_dna: dict) -> BusinessDNA:
        """Insert a new Business DNA profile, flush, and refresh it.

        Args:
            business_dna: Field values for the new ``BusinessDNA`` row.

        Returns:
            The newly created and refreshed ``BusinessDNA``.
        """
        new_business_dna = BusinessDNA(**business_dna)
        self._db.add(new_business_dna)
        await self._db.flush()
        await self._db.refresh(new_business_dna)
        return new_business_dna

    async def get_business_dna_by_id(self, business_dna_id: uuid.UUID) -> BusinessDNA | None:
        """Get a single Business DNA profile by its own id.

        RLS already restricts this to the caller's current org.
        """
        return await self._db.get(BusinessDNA, business_dna_id)

    async def get_business_dna_by_organization_id(
        self, organization_id: uuid.UUID
    ) -> BusinessDNA | None:
        """Get the org's Business DNA profile, if one has been created yet.

        This is the primary lookup for the module — ``business_dna`` is a
        one-row-per-org table with no separate index by any other key, so
        every read and the ``PUT`` upsert's existence check go through this.
        """
        stmt = select(BusinessDNA).where(BusinessDNA.organization_id == organization_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_business_dna(self, business_dna: BusinessDNA, data: dict) -> BusinessDNA:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            business_dna: The ``BusinessDNA`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``BusinessDNA``.
        """
        for field, value in data.items():
            setattr(business_dna, field, value)
        await self._db.flush()
        await self._db.refresh(business_dna)
        return business_dna


class BusinessDNACoreValueRepository:
    """Handles persistence for an organization's Business DNA core values."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_core_value(self, core_value: dict) -> BusinessDNACoreValue:
        """Insert a new core value, flush, and refresh it.

        Args:
            core_value: Field values for the new ``BusinessDNACoreValue`` row.

        Returns:
            The newly created and refreshed ``BusinessDNACoreValue``.
        """
        new_core_value = BusinessDNACoreValue(**core_value)
        self._db.add(new_core_value)
        await self._db.flush()
        await self._db.refresh(new_core_value)
        return new_core_value

    async def get_core_value_by_id(
        self, core_value_id: uuid.UUID
    ) -> BusinessDNACoreValue | None:
        """Get a single core value by its own id.

        RLS already restricts this to the caller's current org.
        """
        return await self._db.get(BusinessDNACoreValue, core_value_id)

    async def list_core_values_by_business_dna_id(
        self, business_dna_id: uuid.UUID
    ) -> list[BusinessDNACoreValue]:
        """List every core value belonging to a Business DNA profile.

        No pagination — this is a short list of values HR typed in during
        onboarding, not an append-heavy or user-generated collection.
        """
        stmt = select(BusinessDNACoreValue).where(
            BusinessDNACoreValue.business_dna_id == business_dna_id
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_core_value(
        self, core_value: BusinessDNACoreValue, data: dict
    ) -> BusinessDNACoreValue:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            core_value: The ``BusinessDNACoreValue`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``BusinessDNACoreValue``.
        """
        for field, value in data.items():
            setattr(core_value, field, value)
        await self._db.flush()
        await self._db.refresh(core_value)
        return core_value

    async def delete_core_value(self, core_value: BusinessDNACoreValue) -> None:
        """Hard-delete a core value.

        Unlike departments/positions/employees, core values have no
        delete-blocked-while-referenced rule and no soft-delete column —
        nothing else in the schema references a core value row, and
        ``audit_log`` (not a retained row) is what preserves "this value
        used to exist" history. See 08_DECISIONS.md 2026-09-21.
        """
        await self._db.delete(core_value)
        await self._db.flush()
