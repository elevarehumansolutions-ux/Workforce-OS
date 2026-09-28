"""Celery tasks for AI suggestion generation."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.model_registry  # noqa: F401 - registers every model, as the app entrypoint does
from app.core.celery_app import celery
from app.core.config import settings
from app.core.fiscal import is_due_for_quarterly_review
from app.core.task_names import AI_GENERATE_SUGGESTIONS_TASK
from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.service import NotificationService
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.repository import MembershipRepository, OrganizationRepository

from .generation import (
    generate_critical_position_suggestions,
    generate_missing_department_suggestions,
    generate_revenue_allocation_suggestions,
)
from .llm import LLMOutputError

logger = logging.getLogger(__name__)

# The single source of truth is app.core.task_names — Org Structure/OKR
# enqueue this task by that same constant, without ever importing this
# module (dependency direction: they sit underneath AI Suggestions).
GENERATE_SUGGESTIONS_TASK = AI_GENERATE_SUGGESTIONS_TASK

# Retried by Celery: the call never reached a real answer, and trying again
# may succeed — a dropped connection or timeout, a rate limit, or Anthropic's
# own 5xx. The SDK already retries these itself (twice, by default) before
# raising, so a retry here is for outages longer than that. Deliberately
# excludes every other APIStatusError subclass (BadRequestError,
# AuthenticationError, PermissionDeniedError, NotFoundError, ...): those mean
# the request itself was wrong, and retrying sends the identical bad request
# again. Also excludes LLMOutputError (Claude answered, but with a refusal,
# a cut-off reply, or an answer that was mostly invented) — the prompt is
# what's broken there, not the connection, so a blind retry just repeats it.
_RETRYABLE_ANTHROPIC_ERRORS = (
    anthropic.APIConnectionError,  # covers APITimeoutError too, a subclass
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)

async def _notify_hr_admins_of_new_suggestions(
    db: AsyncSession, organization_id: uuid.UUID, created_count: int
) -> None:
    """Tell every active HR Administrator that new suggestions are waiting for them.

    Never commits — rides the same transaction as the suggestions it's
    reporting on, so the notification and the rows it points at either
    both land or neither does.
    """
    recipient_ids = await MembershipRepository(db).list_active_user_ids_by_role(
        organization_id, MembershipRole.HR_ADMINISTRATOR.value
    )
    if not recipient_ids:
        return
    plural = "suggestion" if created_count == 1 else "suggestions"
    await NotificationService(db).notify(
        organization_id=organization_id,
        recipient_user_ids=recipient_ids,
        category=NotificationCategory.AI_SUGGESTION,
        title=f"{created_count} new AI {plural} ready for review",
        link_type="ai_suggestions",
    )


async def run_generation(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Run every built generation type for one organization, then commit once.

    One commit (and, if anything was created, one notification) for the
    whole batch — not one per suggestion type — so a reviewer sees "5 new
    suggestions" instead of two separate notifications a few lines apart.
    """
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    created = [
        *await generate_critical_position_suggestions(db, organization_id=organization_id),
        *await generate_revenue_allocation_suggestions(db, organization_id=organization_id),
        *await generate_missing_department_suggestions(db, organization_id=organization_id),
    ]
    if created:
        await _notify_hr_admins_of_new_suggestions(db, organization_id, len(created))
    await db.commit()
    return len(created)

async def _generate(organization_id: uuid.UUID) -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_generation(db, organization_id)
    finally:
        await engine.dispose()

@celery.task(
    bind=True,
    name=GENERATE_SUGGESTIONS_TASK,
    autoretry_for=_RETRYABLE_ANTHROPIC_ERRORS,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def generate_suggestions(self, organization_id: str) -> int:
    """Generate AI suggestions for one organization; returns how many were created.

    Retries automatically (see ``_RETRYABLE_ANTHROPIC_ERRORS``) on a
    transient Anthropic failure. A malformed request or an unusable reply
    (``LLMOutputError``) fails the task instead — retrying the same broken
    prompt or the same bad request would just fail the same way again.
    """
    try:
        return asyncio.run(_generate(uuid.UUID(organization_id)))
    except LLMOutputError:
        logger.error("Suggestion generation for org %s got no usable answer", organization_id)
        raise


QUARTERLY_REVIEW_TASK = "app.modules.ai.tasks.quarterly_objective_review"

# The Beat schedule below runs this once daily; the lookback exceeds that
# interval so a boundary landing between two runs is never missed (a small
# accepted cost: an org very rarely gets included by both of two
# consecutive runs near the edge of the window — harmless, since
# generate_suggestions is fully idempotent either way).
_QUARTERLY_REVIEW_LOOKBACK = timedelta(hours=26)


async def _find_orgs_due_for_quarterly_review(db: AsyncSession) -> list[uuid.UUID]:
    """Which organizations' fiscal quarter just turned over, per the lookback window."""
    now = datetime.now(UTC)
    orgs = await OrganizationRepository(db).list_fiscal_months_for_quarterly_review()
    return [
        organization_id
        for organization_id, fiscal_year_start_month in orgs
        if is_due_for_quarterly_review(fiscal_year_start_month, now, _QUARTERLY_REVIEW_LOOKBACK)
    ]


async def run_quarterly_review(db: AsyncSession) -> int:
    """Enqueue a generation run for every organization whose fiscal quarter just turned over.

    The scheduled half of "recurring, not one-time" (01_REQUIREMENTS.md
    workflow #4) — event triggers (a department marked critical, a new
    position, a new objective) are the other half. This also unblocks the
    rejected-suggestion quarterly suppression: a suggestion held back
    "until the next Quarterly Objective Review" needs some run to actually
    ask again once the quarter has turned, even for an organization with
    zero organic activity that quarter.

    Enqueues each due organization's normal generation task by name — the
    same message ``trigger_ai_suggestion_generation`` publishes, without
    its debounce (unneeded here: this only fires once per organization per
    quarter boundary already, by construction).

    Returns:
        How many organizations were enqueued.
    """
    due_organization_ids = await _find_orgs_due_for_quarterly_review(db)
    for organization_id in due_organization_ids:
        celery.send_task(AI_GENERATE_SUGGESTIONS_TASK, args=[str(organization_id)])
    return len(due_organization_ids)


async def _run_quarterly_review() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_quarterly_review(db)
    finally:
        await engine.dispose()


@celery.task(
    bind=True,
    name=QUARTERLY_REVIEW_TASK,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def quarterly_objective_review(self) -> int:
    """Beat-scheduled: find and enqueue every organization due for its Quarterly Objective Review.

    Retries broadly (unlike ``generate_suggestions``): this task only does
    infrastructure work (one DB read, some Redis publishes), no LLM call,
    so there's no "malformed request" failure mode to exclude from retry —
    every failure here is plausibly transient, matching this codebase's
    existing convention for infra-only tasks (see auth/tasks.py).
    """
    return asyncio.run(_run_quarterly_review())
