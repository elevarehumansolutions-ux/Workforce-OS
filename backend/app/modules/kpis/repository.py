"""Data-access layer for the KPI module."""

from datetime import date, datetime, UTC
import decimal
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import KPI, KPIScore
from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from app.modules.organization.models import Department


class KPIRepository:
    """handles persistence for KPIs within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db
    
    async def create_kpi(self, kpi: dict) -> KPI:
        """Insert a new KPI, flush, and refresh it from the database.

        Args:
            kpi: Field values for the new ``KPI`` row.

        Returns:
            The newly created and refreshed ``KPI``.
        """
        new_kpi = KPI(**kpi)
        self._db.add(new_kpi)
        await self._db.flush()
        await self._db.refresh(new_kpi)
        return new_kpi
    
    async def get_kpi_by_id(self, kpi_id: uuid.UUID) -> KPI | None:
        """Get a single KPI by its own id.

        RLS already restricts this to the caller's current org.

        Args:
            kpi_id: Id of the KPI to fetch.

        Returns:
            The matching non-deleted ``KPI``, or ``None`` if not found.
        """
        stmt = select(KPI).where(
            KPI.id == kpi_id,
            KPI.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_kpis(
        self,
        organization_id: uuid.UUID,
        department_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted KPIs for an organization, newest first.

        Args:
            organization_id: Organization to list KPIs for.
            department_id: If given, restrict results to this department.
            location_id: If given, restrict results to this location.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``KPI`` rows.
        """
        stmt = (
            select(KPI)
            .where(
                KPI.organization_id == organization_id,
                KPI.deleted_at.is_(None)
            )
            .order_by(KPI.created_at.desc())
        )

        if department_id:
            stmt = stmt.where(KPI.department_id == department_id)
        if location_id:
            stmt = stmt.where(KPI.location_id == location_id)

        return await paginate(stmt, page, limit, self._db)
    
    async def sum_weights_for_group(
        self,
        department_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        exclude_kpi_id: uuid.UUID | None = None,
    ) -> decimal.Decimal:
        """Sum non-deleted KPI weights in one department/location group.

        ``location_id=None`` means the department-wide group specifically,
        not "don't filter by location" — unlike ``list_kpis``'s filters,
        this method has no "show everything" mode, since a weight only
        ever means something within one exact group.

        Args:
            department_id: The group's department.
            location_id: The group's location, or ``None`` for the
                department-wide group.
            exclude_kpi_id: If given, leave this KPI's own weight out of
                the sum — used when editing/deleting a KPI, so the
                service layer can add back its *new* weight itself.

        Returns:
            The sum of matching weights, or ``0`` if the group is empty.
        """
        stmt = select(
            func.coalesce(
                func.sum(KPI.weight), 0
            )
        ).where(
            KPI.department_id == department_id,
            KPI.deleted_at.is_(None),
        )

        if location_id is None:
            stmt = stmt.where(KPI.location_id.is_(None))
        else:
            stmt = stmt.where(KPI.location_id == location_id)
        
        if exclude_kpi_id:
            stmt = stmt.where(
                KPI.id != exclude_kpi_id,
            )

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() or decimal.Decimal("0")
    
    async def update_kpi(self, kpi: KPI, data: dict) -> KPI:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            kpi: The ``KPI`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``KPI``.
        """
        for field, value in data.items():
            setattr(kpi, field, value)
        await self._db.flush()
        await self._db.refresh(kpi)
        return kpi

    async def soft_delete_kpi(self, kpi: KPI) -> KPI:
        """Mark a KPI as deleted by stamping ``deleted_at``.

        Args:
            kpi: The ``KPI`` instance to soft-delete.

        Returns:
            The soft-deleted and refreshed ``KPI``.
        """
        kpi.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(kpi)
        return kpi
    
    async def list_kpis_in_group(
        self,
        department_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
    ) -> list[KPI]:
        """Every non-deleted KPI in one exact department/location group.

        Unpaginated, unlike ``list_kpis`` — the group reconcile needs to
        see *all* of a group's KPIs to correctly work out what's being
        created, updated, or deleted; missing a row past a page boundary
        would silently corrupt that diff. Same ``location_id`` handling
        as ``sum_weights_for_group``, for the same reason.

        Args:
            department_id: The group's department.
            location_id: The group's location, or ``None`` for the
                department-wide group.

        Returns:
            Every matching non-deleted ``KPI``.
        """
        stmt = select(KPI).where(
            KPI.department_id == department_id,
            KPI.deleted_at.is_(None),
        )
        if location_id is None:
            stmt = stmt.where(KPI.location_id.is_(None))
        else:
            stmt = stmt.where(KPI.location_id == location_id)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_candidate_kpi_groups_for_weight_suggestion(
        self, organization_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str, uuid.UUID | None]]:
        """Department/location KPI groups worth proposing a fresh weight split for.

        A candidate is any group with 2+ non-deleted KPIs — with only one
        KPI there's nothing to split. Like ``revenue_allocation``
        (08_DECISIONS.md 2026-09-24), a group that already sums to 100 is
        still a candidate: the org's KPI set can change between runs, and
        that's exactly where a genuinely better re-proposal would come
        from — the existing pending-duplicate index and rejection
        suppression are what stop a re-run from nagging, not a
        candidate-side filter.

        Args:
            organization_id: Organization to look in.

        Returns:
            ``(department_id, department_name, location_id)`` for each
            qualifying group, ordered by department creation (with id as
            a tie-breaker) so a retried run sees the same groups in the
            same order.
        """
        stmt = (
            select(KPI.department_id, Department.name, KPI.location_id)
            .join(Department, Department.id == KPI.department_id)
            .where(
                KPI.organization_id == organization_id,
                KPI.deleted_at.is_(None),
            )
            .group_by(KPI.department_id, Department.name, KPI.location_id, Department.created_at, Department.id)
            .having(func.count(KPI.id) >= 2)
            .order_by(Department.created_at.asc(), Department.id.asc())
        )
        result = await self._db.execute(stmt)
        return [tuple(row) for row in result.all()]



class KPIScoreRepository:
    """Handles persistence for KPI scores within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_kpi_score(self, score: dict) -> "KPIScore":
        """Insert a new KPIScore, flush, and refresh it from the database.

        Args:
            score: Field values for the new ``KPIScore`` row.

        Returns:
            The newly created and refreshed ``KPIScore``.
        """
        new_score = KPIScore(**score)
        self._db.add(new_score)
        await self._db.flush()
        await self._db.refresh(new_score)
        return new_score
    
    async def get_score_for_period(
        self,
        kpi_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> KPIScore | None:
        """Get this KPI's score row for one exact period, if it exists.

        This is what decides create-vs-update for the scores upsert — the
        service layer calls this first, then either creates a new row or
        updates the one this returns.

        Args:
            kpi_id: KPI to look up.
            period_start: Start date of the scoring period.
            period_end: End date of the scoring period.

        Returns:
            The matching ``KPIScore``, or ``None`` if this period has no
            score recorded yet.
        """
        stmt = select(KPIScore).where(
            KPIScore.kpi_id == kpi_id,
            KPIScore.period_start == period_start,
            KPIScore.period_end == period_end,
        )
        
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_scores_for_kpi(
        self,
        kpi_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted scores for a KPI, newest first.

        Args:
            kpi_id: KPI whose scores to list.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``KPIScore`` rows.
        """
        stmt = (
            select(KPIScore)
            .where(
                KPIScore.kpi_id == kpi_id,
            )
            .order_by(KPIScore.period_start.desc())
        )
        return await paginate(stmt, page, limit, self._db)
    
    async def update_score(self, score: KPIScore, data: dict) -> KPIScore:
        """Apply a partial update. Caller (service layer) commits.

        Args:
            score: The ``KPIScore`` instance to update in place.
            data: Mapping of field names to their new values.

        Returns:
            The updated and refreshed ``KPIScore``.
        """
        for field, value in data.items():
            setattr(score, field, value)
        await self._db.flush()
        await self._db.refresh(score)
        return score

