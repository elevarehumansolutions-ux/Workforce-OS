"""Data-access layer for the OKR module.

Provides CRUD and lookup operations for OKRs and key results. Every
repository operates within the caller's RLS-scoped session and only
flushes (never commits) — commits are the service layer's responsibility.
No delete operations exist here — ``DELETE`` is deferred to M8 (see
``08_DECISIONS.md`` 2026-09-21).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from .models import KeyResult, OKR


class OKRRepository:
    """Handles persistence for OKRs within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_okr(self, okr: dict) -> OKR:
        """Insert a new OKR, flush, and refresh it from the database.

        Args:
            okr: Field values for the new ``OKR`` row.

        Returns:
            The newly created and refreshed ``OKR``.
        """
        new_okr = OKR(**okr)
        self._db.add(new_okr)
        await self._db.flush()
        await self._db.refresh(new_okr)
        return new_okr

    async def get_okr_by_id(self, okr_id: uuid.UUID) -> OKR | None:
        """Get a single OKR by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            okr_id: Id of the OKR to fetch.

        Returns:
            The matching non-deleted ``OKR``, or ``None`` if not found.
        """
        stmt = select(OKR).where(
            OKR.id == okr_id,
            OKR.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_okrs(
        self,
        organization_id: uuid.UUID,
        department_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted OKRs for an organization, oldest first.

        Args:
            organization_id: Organization to list OKRs for.
            department_id: If given, restrict results to this department.
            location_id: If given, restrict results to this location.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``OKR`` rows.
        """
        stmt = select(OKR).where(
            OKR.organization_id == organization_id,
            OKR.deleted_at.is_(None),
        )
        if department_id is not None:
            stmt = stmt.where(OKR.department_id == department_id)
        if location_id is not None:
            stmt = stmt.where(OKR.location_id == location_id)
        stmt = stmt.order_by(OKR.created_at.asc())
        return await paginate(stmt, page, limit, self._db)

    async def update_okr(self, okr: OKR, data: dict) -> OKR:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            okr: The ``OKR`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``OKR``.
        """
        for field, value in data.items():
            setattr(okr, field, value)
        await self._db.flush()
        await self._db.refresh(okr)
        return okr


class KeyResultRepository:
    """Handles persistence for key results belonging to an OKR."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_key_result(self, key_result: dict) -> KeyResult:
        """Insert a new key result, flush, and refresh it from the database.

        Args:
            key_result: Field values for the new ``KeyResult`` row.

        Returns:
            The newly created and refreshed ``KeyResult``.
        """
        new_key_result = KeyResult(**key_result)
        self._db.add(new_key_result)
        await self._db.flush()
        await self._db.refresh(new_key_result)
        return new_key_result

    async def get_key_result_by_id(self, key_result_id: uuid.UUID) -> KeyResult | None:
        """Get a single key result by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            key_result_id: Id of the key result to fetch.

        Returns:
            The matching non-deleted ``KeyResult``, or ``None`` if not found.
        """
        stmt = select(KeyResult).where(
            KeyResult.id == key_result_id,
            KeyResult.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_key_results(
        self, okr_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted key results for an OKR, oldest first.

        Args:
            okr_id: OKR to list key results for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``KeyResult`` rows.
        """
        stmt = (
            select(KeyResult)
            .where(
                KeyResult.okr_id == okr_id,
                KeyResult.deleted_at.is_(None),
            )
            .order_by(KeyResult.created_at.asc())
        )
        return await paginate(stmt, page, limit, self._db)

    async def update_key_result(self, key_result: KeyResult, data: dict) -> KeyResult:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            key_result: The ``KeyResult`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``KeyResult``.
        """
        for field, value in data.items():
            setattr(key_result, field, value)
        await self._db.flush()
        await self._db.refresh(key_result)
        return key_result
