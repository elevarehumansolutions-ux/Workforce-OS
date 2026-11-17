"""The Scoring module's side of the notice board (app/core/events.py).

The KPI module announces "a result was saved". This is how the Scoring module hears about it,
so the department's figures follow the number HR just typed instead of waiting for the night.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events

from .service import ScoringService


async def on_kpi_result_saved(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    kpi_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> None:
    """A KPI result was saved: refresh the open quarter's department figures."""
    await ScoringService(db).refresh_departments_after_result(organization_id, period_start, datetime.now(UTC))


def register_listeners() -> None:
    """Sign the Scoring module up for KPI events. Safe to call more than once."""
    events.subscribe(events.KPI_RESULT_SAVED, on_kpi_result_saved)
