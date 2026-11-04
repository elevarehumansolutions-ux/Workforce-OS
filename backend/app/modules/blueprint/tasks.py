"""Celery job that proposes a blueprint for one organization."""

import asyncio
import logging
import uuid

import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.model_registry  # noqa: F401 - registers every model, as the app entrypoint does
from app.core.celery_app import celery
from app.core.config import settings
from app.core.task_names import BLUEPRINT_GENERATE_TASK
from app.modules.ai.llm import LLMOutputError
from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.service import NotificationService
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.repository import MembershipRepository

from .generation import generate_blueprint
from .repository import BlueprintRepository

logger = logging.getLogger(__name__)

# Same rule as AI suggestions: retry only when the call never reached a real answer.
_RETRYABLE_ANTHROPIC_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


async def run_blueprint_generation(
    db: AsyncSession, organization_id: uuid.UUID, first_time_only: bool
) -> int:
    """Generate for one organization, tell HR, and commit once. Returns how many items were saved."""
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
    if first_time_only and await BlueprintRepository(db).has_any_items(organization_id):
        return 0

    items = await generate_blueprint(db, organization_id)
    if items:
        recipient_ids = await MembershipRepository(db).list_active_user_ids_by_role(
            organization_id, MembershipRole.HR_ADMINISTRATOR.value
        )
        if recipient_ids:
            await NotificationService(db).notify(
                organization_id=organization_id,
                recipient_user_ids=recipient_ids,
                category=NotificationCategory.AI_SUGGESTION,
                title="Your suggested departments, positions and objectives are ready to review",
                link_type="blueprint",
            )
    await db.commit()
    return len(items)


async def _generate(organization_id: uuid.UUID, first_time_only: bool) -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await run_blueprint_generation(db, organization_id, first_time_only)
    finally:
        await engine.dispose()


@celery.task(
    bind=True,
    name=BLUEPRINT_GENERATE_TASK,
    autoretry_for=_RETRYABLE_ANTHROPIC_ERRORS,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def generate_blueprint_task(self, organization_id: str, first_time_only: bool = False) -> int:
    """Propose departments, positions, objectives and key results for one organization."""
    try:
        return asyncio.run(_generate(uuid.UUID(organization_id), first_time_only))
    except LLMOutputError:
        logger.error("Blueprint generation for org %s got no usable answer", organization_id)
        raise
