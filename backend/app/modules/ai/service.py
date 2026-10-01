"""Business logic for AI suggestions.

Never commits — the caller (a router, or the Celery task that drives
generation) owns the transaction. Committing per suggestion would end the
transaction that ``app.current_org_id`` is scoped to, leaving every
following suggestion in the same batch with no tenant context.
"""

from app.modules.ai.schemas import AISuggestionEditRequest
import uuid
from datetime import UTC, datetime
from typing import NoReturn

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    OrganizationNotFoundException,
    SuggestionAlreadyReviewedException,
    SuggestionNotFoundException,
    ValidationException,
)
from app.core.fiscal import get_fiscal_quarter_start
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.service import AuditService
from app.modules.organization.service import PositionService, DepartmentService
from app.modules.kpis.service import KPIService
from app.modules.kpis.schemas import KPIUpdate
from app.modules.tenancy_identity.repository import OrganizationRepository

from .enums import SuggestionStatus, SuggestionType
from .models import AISuggestion
from .repository import AISuggestionRepository
from .schemas import AISuggestionCreateRequest, AISuggestionResponse

_EDITABLE_FIELDS = {
    SuggestionType.CRITICAL_POSITION.value: {"criticality_type", "risk_level"},
    SuggestionType.REVENUE_ALLOCATION.value: {"revenue_allocation_percentage"},
    SuggestionType.MISSING_DEPARTMENT.value: {"department_name"},
    SuggestionType.KPI_WEIGHT.value: {"weight"},
}


class AISuggestionService:
    """Orchestrates creation and review of AI-proposed suggestions."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with an RLS-scoped async session."""
        self._repo = AISuggestionRepository(db)
        self._org_repo = OrganizationRepository(db)
        self._audit = AuditService(db)
        self._position_service = PositionService(db)
        self._department_service = DepartmentService(db)
        self._kpi_service = KPIService(db)

    async def _raise_not_reviewable(self, suggestion_id: uuid.UUID) -> NoReturn:
        """Explain why an atomic review changed nothing: 404 if unseen, else 409."""
        if await self._repo.get_suggestion_by_id(suggestion_id) is None:
            raise SuggestionNotFoundException()
        raise SuggestionAlreadyReviewedException()
    
    async def _apply_reviewed_values(
        self,
        suggestion: AISuggestion,
        actor_user_id: uuid.UUID,
    ) -> None:
        """Write a reviewed suggestion's values onto the real row, via Org Structure's services.

        Reads only the ``reviewed_*`` columns, so approval (the AI's values,
        copied across by the claim) and edit (HR's values) share it.
        """
        if suggestion.suggestion_type == SuggestionType.CRITICAL_POSITION.value:
            # A critical_position suggestion always carries both values
            # (schema + database CHECK, 08_DECISIONS.md 2026-09-24).
            await self._position_service.update_position(
                suggestion.position_id,
                actor_user_id,
                {
                    "is_critical": True,
                    "criticality_type": suggestion.reviewed_criticality_type,
                    "risk_level": suggestion.reviewed_risk_level,
                },
            )
        elif suggestion.suggestion_type == SuggestionType.REVENUE_ALLOCATION.value:
            await self._department_service.update_department(
                suggestion.department_id,
                actor_user_id,
                {
                    "revenue_allocation_percentage": (
                        suggestion.reviewed_revenue_allocation_percentage
                    ),
                },
            )
        elif suggestion.suggestion_type == SuggestionType.MISSING_DEPARTMENT.value:
            await self._department_service.create_department(
                suggestion.organization_id,
                actor_user_id,
                {"name": suggestion.reviewed_department_name},
            )
        elif suggestion.suggestion_type == SuggestionType.KPI_WEIGHT.value:
            # Reuses the exact weight-sum-to-100 validation KPIService
            # already enforces on every edit (08_DECISIONS.md 2026-09-29/
            # 2026-09-30) — no separate check needed here. If applying it
            # would push the group over 100%, update_kpi raises
            # KPIWeightConflictException, which rolls this approval back
            # too, same as a failed write-through for the other three types.
            await self._kpi_service.update_kpi(
                suggestion.kpi_id,
                actor_user_id,
                KPIUpdate(weight=suggestion.reviewed_weight),
            )
        else:
            raise NotImplementedError(suggestion.suggestion_type)

    async def create_suggestion_if_eligible(
        self,
        organization_id: uuid.UUID,
        data: AISuggestionCreateRequest,
    ) -> AISuggestionResponse | None:
        """Create a pending suggestion unless one of three rules blocks it.

        Rule 1 (rejected-suggestion quarterly suppression, 08_DECISIONS.md
        2026-09-22): skipped if the same target was rejected within the
        org's current fiscal quarter. Rule 2 (backlog cap, 2026-09-25):
        a ``missing_department`` is skipped while the org already has
        ``ai_max_pending_missing_departments`` of them awaiting review — the
        one type that names something new, so the one that can flood the
        queue. It's a soft cap: two runs racing can overshoot it by a few.
        Rule 3 (pending-duplicate, database enforced): skipped if the same
        target already has a pending suggestion. All are quiet no-ops, not
        errors — a retry or a repeated trigger is expected, not exceptional.

        Args:
            organization_id: Organization to create the suggestion for.
            data: The candidate suggestion.

        Returns:
            The created suggestion, or ``None`` if it was skipped.

        Raises:
            OrganizationNotFoundException: If the organization isn't
                visible under the current tenant context.
        """
        organization = await self._org_repo.get_organization_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundException()

        fiscal_quarter_start = get_fiscal_quarter_start(
            organization.fiscal_year_start_month, datetime.now(UTC)
        )
        if await self._repo.has_recent_rejection(
            organization_id,
            data.suggestion_type,
            data.position_id,
            data.department_id,
            data.suggested_department_name,
            fiscal_quarter_start,
        ):
            return None

        if (
            data.suggestion_type == SuggestionType.MISSING_DEPARTMENT.value
            and await self._repo.count_pending(organization_id, data.suggestion_type)
            >= settings.ai_max_pending_missing_departments
        ):
            return None

        suggestion = await self._repo.create_pending_suggestion(
            {**data.model_dump(), "organization_id": organization_id}
        )
        if suggestion is None:
            return None
        return AISuggestionResponse.model_validate(suggestion)

    async def reject_suggestion(
        self,
        suggestion_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> AISuggestionResponse:
        """Reject a pending suggestion and record who did it.

        Setting ``reviewed_at`` here is what starts the rejected-suggestion
        quarterly suppression (08_DECISIONS.md 2026-09-22).

        Args:
            suggestion_id: Id of the suggestion to reject.
            actor_user_id: User making the decision, for the audit log.

        Returns:
            The rejected suggestion.

        Raises:
            SuggestionNotFoundException: If no such suggestion is visible
                to the caller's organization.
            SuggestionAlreadyReviewedException: If it is no longer pending.
        """
        suggestion = await self._repo.reject_pending_suggestion(
            suggestion_id, actor_user_id
        )
        if suggestion is None:
            # Nothing changed: it doesn't exist (or isn't ours), or someone
            # already reviewed it. The lookup tells the two apart.
            await self._raise_not_reviewable(suggestion_id)

        await self._audit.log_action(
            organization_id=suggestion.organization_id,
            actor_user_id=actor_user_id,
            action="reject",
            entity_type="ai_suggestion",
            entity_id=suggestion.id,
            changes={
                "old": {"status": SuggestionStatus.PENDING.value},
                "new": {"status": SuggestionStatus.REJECTED.value},
            },
        )
        return AISuggestionResponse.model_validate(suggestion)

    async def approve_suggestion(
        self,
        suggestion_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> AISuggestionResponse:
        """Approve a pending suggestion as proposed and apply it.

        Claims the suggestion atomically first, so only the winning reviewer
        applies it. If applying it then fails, the caller's transaction rolls
        back and the suggestion is pending again.

        Args:
            suggestion_id: Id of the suggestion to approve.
            actor_user_id: User making the decision.

        Returns:
            The approved suggestion.

        Raises:
            SuggestionNotFoundException: If no such suggestion is visible
                to the caller's organization.
            SuggestionAlreadyReviewedException: If it is no longer pending.
        """
        suggestion = await self._repo.approve_pending_suggestion(
            suggestion_id, actor_user_id
        )
        if suggestion is None:
            await self._raise_not_reviewable(suggestion_id)

        await self._apply_reviewed_values(suggestion, actor_user_id)

        await self._audit.log_action(
            organization_id=suggestion.organization_id,
            actor_user_id=actor_user_id,
            action="approve",
            entity_type="ai_suggestion",
            entity_id=suggestion.id,
            changes={
                "old": {"status": SuggestionStatus.PENDING.value},
                "new": {"status": SuggestionStatus.APPROVED.value},
            },
        )
        return AISuggestionResponse.model_validate(suggestion)

    @staticmethod
    def _validate_edit(suggestion: AISuggestion, edits: dict) -> None:
        """Refuse an edit that doesn't fit the suggestion's type or changes nothing.

        Args:
            suggestion: The suggestion being edited.
            edits: Only the fields the reviewer actually supplied.

        Raises:
            ValidationException: If a field doesn't apply to this suggestion
                type, or every supplied value equals what the AI proposed.
        """
        not_applicable = set(edits) - _EDITABLE_FIELDS[suggestion.suggestion_type]
        if not_applicable:
            raise ValidationException(
                f"{suggestion.suggestion_type} suggestions can't change: "
                f"{', '.join(sorted(not_applicable))}"

            )
        
        suggested = {
            "criticality_type": suggestion.suggested_criticality_type,
            "risk_level": suggestion.suggested_risk_level,
            "revenue_allocation_percentage": suggestion.suggested_revenue_allocation_percentage,
            "department_name": suggestion.suggested_department_name,
        }

        if (all(suggested[field] == value for field, value in edits.items())):
            raise ValidationException("This edit matches the AI's suggestion; approve it instead")

    async def edit_suggestion(
        self,
        suggestion_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        edit: AISuggestionEditRequest,
    ) -> AISuggestionResponse:
        """Record a reviewer's corrected values, apply them, and audit the edit.

        Args:
            suggestion_id: Id of the suggestion to edit.
            actor_user_id: User making the edit.
            edit: The values the reviewer is changing; the rest keep the AI's.

        Returns:
            The edited suggestion.

        Raises:
            SuggestionNotFoundException: If no such suggestion is visible
                to the caller's organization.
            ValidationException: If a field doesn't apply to this suggestion
                type, or the edit changes nothing.
            SuggestionAlreadyReviewedException: If it is no longer pending.
        """
        suggestion = await self._repo.get_suggestion_by_id(suggestion_id)
        if suggestion is None:
            raise SuggestionNotFoundException()

        edits = edit.model_dump(exclude_none=True)
        self._validate_edit(suggestion, edits)

        edited = await self._repo.edit_pending_suggestion(
            suggestion_id, actor_user_id, **edits
        )
        if edited is None:
            raise SuggestionAlreadyReviewedException()

        await self._apply_reviewed_values(edited, actor_user_id)
        await self._audit.log_action(
            organization_id=edited.organization_id,
            actor_user_id=actor_user_id,
            action="edit",
            entity_type="ai_suggestion",
            entity_id=edited.id,
            changes={
                "old": {"status": SuggestionStatus.PENDING.value},
                "new": {"status": SuggestionStatus.EDITED.value, **jsonable_encoder(edits)},
            },
        )
        return AISuggestionResponse.model_validate(edited)

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
            A paginated response wrapping the matching suggestions.
        """
        return await self._repo.list_suggestions(
            organization_id, status, suggestion_type, page, limit
        )
