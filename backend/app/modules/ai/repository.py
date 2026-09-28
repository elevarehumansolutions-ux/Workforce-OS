"""Data-access layer for the AI module.

Provides persistence for AI-proposed suggestions and LLM usage-log
entries. Every repository operates within the caller's RLS-scoped session
and only flushes (never commits) — the transaction boundary belongs to
whoever owns the unit of work (a router, or a Celery task).
"""

import decimal
import uuid
from datetime import datetime, UTC

from sqlalchemy import Text, cast, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse
from app.core.text import normalized_name_expr

from .models import AISuggestion, AIUsageLog
from .enums import SuggestionStatus, SuggestionType


# The atomic review UPDATEs rely on RETURNING for the truth about what changed.
# Without these options SQLAlchemy also "synchronizes" objects it already holds by
# evaluating the WHERE clause in Python — which can mark an in-memory suggestion
# as reviewed even though the database matched no row (e.g. another org's, hidden
# by RLS). synchronize_session=False stops that; populate_existing=True makes a
# returned row refresh the in-memory object, so the caller sees the real state.
_ATOMIC_UPDATE_OPTIONS = {"synchronize_session": False, "populate_existing": True}


class AISuggestionRepository:
    """Handles persistence for AI-proposed suggestions within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def create_pending_suggestion(self, suggestion: dict) -> AISuggestion | None:
        """Insert a new pending suggestion, or no-op if this target already has one.

        Uses ``INSERT ... ON CONFLICT DO NOTHING`` against the partial
        unique index on (``organization_id``, ``suggestion_type``,
        ``position_id``, ``department_id``,
        ``suggested_department_name_normalized``) ``WHERE status =
        'pending'`` (``08_DECISIONS.md`` 2026-09-07, corrected 2026-09-23
        to add ``NULLS NOT DISTINCT`` and the normalized name). A retried
        or duplicate generation call for the same target becomes a safe
        no-op instead of a duplicate row or a raised ``IntegrityError``.

        Does not handle the separate rejected-suggestion quarterly
        suppression rule (``08_DECISIONS.md`` 2026-09-22) — that's a read
        the caller (service layer) is responsible for doing before ever
        calling this method.

        Args:
            suggestion: Field values for the new ``AISuggestion`` row.
                Must not include ``status`` — this method always inserts
                as pending.

        Returns:
            The newly created ``AISuggestion``, or ``None`` if a pending
            suggestion for this exact target already existed.
        """
        stmt = (
            pg_insert(AISuggestion)
            .values(**suggestion, status=SuggestionStatus.PENDING.value)
            .on_conflict_do_nothing(
                index_elements=[
                    AISuggestion.organization_id,
                    AISuggestion.suggestion_type,
                    AISuggestion.position_id,
                    AISuggestion.department_id,
                    AISuggestion.suggested_department_name_normalized,
                ],
                index_where=(AISuggestion.status == SuggestionStatus.PENDING.value),
            )
            .returning(AISuggestion)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def has_recent_rejection(
        self,
        organization_id: uuid.UUID,
        suggestion_type: str,
        position_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        suggested_department_name: str | None,
        fiscal_quarter_start: datetime,
    ) -> bool:
        """Check whether this exact target was rejected within the current fiscal quarter.

        Backs the rejected-suggestion quarterly suppression rule
        (08_DECISIONS.md 2026-09-22) — the service layer calls this before
        create_pending_suggestion, and skips generating a new pending
        suggestion for this target if it returns True. Deliberately plain
        equality (not is_not_distinct_from) for each target column: the
        caller already knows the concrete value (a real id, or None), so
        SQLAlchemy's existing None-to-IS-NULL handling is sufficient. The
        department name is compared on its normalized key (same expression
        as the generated column, so the two can't drift), so a rejected
        "Customer Success" also suppresses "  customer   success ".

        Args:
            organization_id: Organization to check within.
            suggestion_type: The suggestion type of the target.
            position_id: Target position, if this type uses one.
            department_id: Target department, if this type uses one.
            suggested_department_name: Target department name, if this
                type uses one.
            fiscal_quarter_start: Start of the org's current fiscal
                quarter — a rejection at or after this is still "this
                quarter" and still suppresses regeneration.

        Returns:
            True if a rejected suggestion for this exact target exists
            with reviewed_at on or after fiscal_quarter_start.
        """
        normalized_name = (
            None
            if suggested_department_name is None
            else normalized_name_expr(cast(suggested_department_name, Text))
        )
        stmt = (
            select(AISuggestion.id)
            .where(
                AISuggestion.organization_id == organization_id,
                AISuggestion.suggestion_type == suggestion_type,
                AISuggestion.position_id == position_id,
                AISuggestion.department_id == department_id,
                AISuggestion.suggested_department_name_normalized == normalized_name,
                AISuggestion.status == SuggestionStatus.REJECTED.value,
                AISuggestion.reviewed_at >= fiscal_quarter_start,
            )
            .limit(1)
        )

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_recent_rejected_department_names(
        self, organization_id: uuid.UUID, fiscal_quarter_start: datetime
    ) -> list[str]:
        """List missing-department names rejected within the current fiscal quarter.

        For prompt context: telling Claude what was already rejected costs
        a few tokens and saves a wasted candidate — `has_recent_rejection`
        would silently suppress it anyway, but only after a full round trip
        (and its cost) proposing something guaranteed to be dropped.

        Args:
            organization_id: Organization to check within.
            fiscal_quarter_start: Start of the org's current fiscal
                quarter — matches ``has_recent_rejection``'s own window.

        Returns:
            The rejected names, as originally written (not normalized) —
            good enough for Claude to read, even though matching against
            them uses the normalized key.
        """
        stmt = select(AISuggestion.suggested_department_name).where(
            AISuggestion.organization_id == organization_id,
            AISuggestion.suggestion_type == SuggestionType.MISSING_DEPARTMENT.value,
            AISuggestion.status == SuggestionStatus.REJECTED.value,
            AISuggestion.reviewed_at >= fiscal_quarter_start,
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_pending(self, organization_id: uuid.UUID, suggestion_type: str) -> int:
        """Count an organization's unreviewed suggestions of one type.

        Backs the backlog cap (08_DECISIONS.md 2026-09-25): generation stops
        adding suggestions of a type while too many are still waiting for a
        reviewer.

        Args:
            organization_id: Organization to count within.
            suggestion_type: The suggestion type to count.

        Returns:
            The number of pending suggestions of that type.
        """
        stmt = select(func.count()).where(
            AISuggestion.organization_id == organization_id,
            AISuggestion.suggestion_type == suggestion_type,
            AISuggestion.status == SuggestionStatus.PENDING.value,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def reject_pending_suggestion(
        self,
        suggestion_id: uuid.UUID,
        reviewed_by_user_id: uuid.UUID,
    ) -> AISuggestion | None:
        """Atomically reject a suggestion, but only if it is still pending.

        The pending check is part of the UPDATE itself, so two reviewers
        acting on the same suggestion can't both succeed.

        Args:
            suggestion_id: Id of the suggestion to reject.
            reviewed_by_user_id: The id of the user performing the rejection.

        Returns:
            The rejected ``AISuggestion``, or ``None`` if nothing changed —
            either no such suggestion is visible to the caller, or it was
            already reviewed. The caller decides which.
        """
        stmt = (
            update(AISuggestion)
            .where(
                AISuggestion.id == suggestion_id,
                AISuggestion.status == SuggestionStatus.PENDING.value,
            )
            .values(
                status=SuggestionStatus.REJECTED.value,
                reviewed_at=datetime.now(UTC),
                reviewed_by_user_id=reviewed_by_user_id,
            )
            .returning(AISuggestion)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def get_suggestion_by_id(self, suggestion_id: uuid.UUID) -> AISuggestion | None:
        """Get a single suggestion by its own id, whatever its status.

        RLS already restricts this to the caller's current org. Suggestions
        are never soft-deleted, so there's no ``deleted_at`` filter.

        Args:
            suggestion_id: Id of the suggestion to fetch.

        Returns:
            The matching ``AISuggestion``, or ``None`` if not found.
        """
        stmt = select(AISuggestion).where(AISuggestion.id == suggestion_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def approve_pending_suggestion(
        self,
        suggestion_id: uuid.UUID,
        reviewed_by_user_id: uuid.UUID,
    ) -> AISuggestion | None:
        """Atomically approve a suggestion as proposed, but only if it is still pending.

        The AI's ``suggested_*`` values are copied into the matching
        ``reviewed_*`` columns inside the same UPDATE, so the decision and
        the values it accepted can't drift apart, and two reviewers can't
        both succeed.

        Args:
            suggestion_id: Id of the suggestion to approve.
            reviewed_by_user_id: The id of the user performing the approval.

        Returns:
            The approved ``AISuggestion``, or ``None`` if nothing changed —
            either no such suggestion is visible to the caller, or it was
            already reviewed. The caller decides which.
        """
        stmt = (
            update(AISuggestion)
            .where(
                AISuggestion.id == suggestion_id,
                AISuggestion.status == SuggestionStatus.PENDING.value,
            )
            .values(
                status=SuggestionStatus.APPROVED.value,
                reviewed_at=datetime.now(UTC),
                reviewed_by_user_id=reviewed_by_user_id,
                reviewed_criticality_type=AISuggestion.suggested_criticality_type,
                reviewed_risk_level=AISuggestion.suggested_risk_level,
                reviewed_revenue_allocation_percentage=(
                    AISuggestion.suggested_revenue_allocation_percentage
                ),
                reviewed_department_name=AISuggestion.suggested_department_name,
            )
            .returning(AISuggestion)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()
    
    async def edit_pending_suggestion(
        self,
        suggestion_id: uuid.UUID,
        reviewed_by_user_id: uuid.UUID,
        *,
        criticality_type: str | None = None,
        risk_level: str | None = None,
        revenue_allocation_percentage: decimal.Decimal | None = None,
        department_name: str | None = None,
    ) -> AISuggestion | None:
        """Atomically record a human-edited decision, but only if still pending.

        Each ``reviewed_*`` value is the reviewer's if they supplied one,
        otherwise the AI's ``suggested_*`` value, decided inside the same
        UPDATE (``COALESCE``), so a reviewer can change just one field and
        two reviewers can't both succeed.

        Args:
            suggestion_id: Id of the suggestion to edit.
            reviewed_by_user_id: The id of the user making the edit.
            criticality_type: Reviewer's criticality type, if changing it.
            risk_level: Reviewer's risk level, if changing it.
            revenue_allocation_percentage: Reviewer's percentage, if changing it.
            department_name: Reviewer's department name, if changing it.

        Returns:
            The edited ``AISuggestion``, or ``None`` if nothing changed —
            either no such suggestion is visible to the caller, or it was
            already reviewed. The caller decides which.
        """
        stmt = (
            update(AISuggestion)
            .where(
                AISuggestion.id == suggestion_id,
                AISuggestion.status == SuggestionStatus.PENDING.value,
            )
            .values(
                status=SuggestionStatus.EDITED.value,
                reviewed_at=datetime.now(UTC),
                reviewed_by_user_id=reviewed_by_user_id,
                reviewed_criticality_type=func.coalesce(
                    criticality_type, AISuggestion.suggested_criticality_type
                ),
                reviewed_risk_level=func.coalesce(
                    risk_level, AISuggestion.suggested_risk_level
                ),
                reviewed_revenue_allocation_percentage=func.coalesce(
                    revenue_allocation_percentage,
                    AISuggestion.suggested_revenue_allocation_percentage,
                ),
                reviewed_department_name=func.coalesce(
                    department_name, AISuggestion.suggested_department_name
                ),
            )
            .returning(AISuggestion)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def list_suggestions(
        self,
        organization_id: uuid.UUID,
        status: str | None = None,
        suggestion_type: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List an organization's suggestions, newest first.

        Args:
            organization_id: Organization to list suggestions for.
            status: If given, restrict results to this review status.
            suggestion_type: If given, restrict results to this type.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``AISuggestion`` rows.
        """
        stmt = select(AISuggestion).where(AISuggestion.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(AISuggestion.status == status)
        if suggestion_type is not None:
            stmt = stmt.where(AISuggestion.suggestion_type == suggestion_type)
        stmt = stmt.order_by(AISuggestion.created_at.desc(), AISuggestion.id)
        return await paginate(stmt, page, limit, self._db)


class AIUsageLogRepository:
    """Persistence for the one-row-per-LLM-call usage log."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db
    
    async def create_usage_log(
        self,
        *,
        organization_id: uuid.UUID,
        purpose: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        estimated_cost_usd: decimal.Decimal | None,
    ) -> AIUsageLog:
        """Record one LLM call. Flushes but never commits."""
        row = AIUsageLog(
            organization_id=organization_id,
            purpose=purpose,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
        self._db.add(row)
        await self._db.flush()
        return row
