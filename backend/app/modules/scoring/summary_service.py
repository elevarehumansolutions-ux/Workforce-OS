"""Writing and keeping the executive summary of an organization's period (M12 slice G).

08_DECISIONS.md 2026-10-21, question 10: a weekly "so far" summary replaces the
previous week's, skipped when the facts have not changed; one final summary is
written when the quarter has closed and is then frozen. Services flush via the
repository but never commit: the Celery job owns the transaction.
"""

import uuid
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.repository import DepartmentRepository
from app.modules.tasks.periods import current_fiscal_quarter
from app.modules.tasks.service import TaskService
from app.modules.tenancy_identity.repository import OrganizationRepository

from .company import CompanyNumbers, previous_quarter_dates, range_moments
from .repository import ScoringRepository
from .service import ScoringService, period_dates
from .summary_facts import MIN_VALID_TASKS_FOR_SUMMARY, build_fact_sheet, change, fingerprint, number
from .summary_generation import write_summary


class ExecutiveSummaryService:
    """Builds the fact sheet from saved scores and writes the period's summary."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = ScoringRepository(db)
        self._department_repo = DepartmentRepository(db)
        self._organization_repo = OrganizationRepository(db)
        self._task_service = TaskService(db)

    async def _build_sheet(
        self, organization, current: tuple[date, date], period_is_closed: bool
    ) -> dict | None:
        """The fact sheet for a period, or ``None`` if there is not enough data to summarise.

        "Not enough" means no saved department rows, or fewer than 10 valid
        tasks in the period (question 11: an AI call on almost nothing writes filler).
        """
        previous = previous_quarter_dates(current[0], current[1])
        departments = await ScoringService._every_item(
            lambda page, limit: self._department_repo.list_departments(organization.id, page, limit)
        )
        names = {department.id: department.name for department in departments}

        current_rows = {}
        previous_rows = {}
        for row in await self._repo.list_department_scores_for_periods([previous, current]):
            if row.department_id not in names:
                continue
            if (row.period_start, row.period_end) == current:
                current_rows[row.department_id] = row
            else:
                previous_rows[row.department_id] = row
        if len(current_rows) == 0:
            return None

        now_numbers = CompanyNumbers(list(current_rows.values()))
        before_numbers = CompanyNumbers(list(previous_rows.values())) if previous_rows else None
        valid_tasks = now_numbers.on_time + now_numbers.late + now_numbers.not_done
        if valid_tasks < MIN_VALID_TASKS_FOR_SUMMARY:
            return None

        company = {
            "headline": number(now_numbers.headline_score),
            "headline_change": change(
                now_numbers.headline_score, before_numbers.headline_score if before_numbers else None
            ),
            "departments_counted": now_numbers.departments_counted,
            "departments_total": len(current_rows),
            "punctuality": number(now_numbers.punctuality_score),
            "punctuality_change": change(
                now_numbers.punctuality_score, before_numbers.punctuality_score if before_numbers else None
            ),
            "tasks_on_time": now_numbers.on_time,
            "tasks_late": now_numbers.late,
            "tasks_not_done": now_numbers.not_done,
        }

        department_facts = []
        for department_id, row in current_rows.items():
            earlier = previous_rows.get(department_id)
            department_facts.append(
                {
                    "name": names[department_id],
                    "goals_score": number(row.kpi_results_score),
                    "goals_change": change(row.kpi_results_score, earlier.kpi_results_score if earlier else None),
                    "punctuality": number(row.punctuality_score),
                    "punctuality_change": change(row.punctuality_score, earlier.punctuality_score if earlier else None),
                }
            )
        department_facts.sort(key=_by_name)

        start, end = range_moments(current[0], current[1], organization.timezone)
        delays = []
        for department_id, category, held_back in await self._task_service.count_approved_blocks_by_category(
            start, end
        ):
            if department_id in names:
                delays.append({"department": names[department_id], "reason": category, "held_back_tasks": held_back})
        delays.sort(key=_delay_order)

        return build_fact_sheet(period_is_closed, company, department_facts, delays)

    async def refresh_current(self, organization_id: uuid.UUID, now: datetime) -> str:
        """Write this week's "so far" summary of the current quarter, unless it would not change.

        Returns:
            What happened: ``"written"``, ``"unchanged"`` (same facts as last time, no model
            call), ``"not_enough_data"`` or ``"frozen"``.
        """
        organization = await self._organization_repo.get_organization_by_id(organization_id)
        current = period_dates(*current_fiscal_quarter(organization.fiscal_year_start_month, organization.timezone, now))

        sheet = await self._build_sheet(organization, current, period_is_closed=False)
        if sheet is None:
            return "not_enough_data"

        existing = await self._repo.get_executive_summary(organization_id, current[0], current[1])
        if existing is not None and existing.finalized_at is not None:
            return "frozen"
        if existing is not None and existing.facts_fingerprint == fingerprint(sheet):
            return "unchanged"

        text, source = await write_summary(self._db, organization_id, sheet)
        await self._repo.save_executive_summary(
            {
                "organization_id": organization_id,
                "period_start": current[0],
                "period_end": current[1],
                "summary_text": text,
                "source": source.value,
                "facts_fingerprint": fingerprint(sheet),
                "generated_at": now,
            }
        )
        return "written"

    async def finalize_previous(self, organization_id: uuid.UUID, now: datetime) -> str:
        """Write the final summary of the quarter that just closed, and freeze it. Done once.

        Only when the quarter's scores are themselves closed (frozen), so the summary is
        written from the numbers that were published.

        Returns:
            ``"finalized"``, ``"period_not_closed"``, ``"already_final"`` or ``"not_enough_data"``.
        """
        organization = await self._organization_repo.get_organization_by_id(organization_id)
        current_start, current_end = current_fiscal_quarter(
            organization.fiscal_year_start_month, organization.timezone, now
        )
        current = period_dates(current_start, current_end)
        previous = previous_quarter_dates(current[0], current[1])

        if not await self._repo.period_is_frozen(organization_id, previous[0], previous[1]):
            return "period_not_closed"
        existing = await self._repo.get_executive_summary(organization_id, previous[0], previous[1])
        if existing is not None and existing.finalized_at is not None:
            return "already_final"

        sheet = await self._build_sheet(organization, previous, period_is_closed=True)
        if sheet is None:
            return "not_enough_data"

        text, source = await write_summary(self._db, organization_id, sheet)
        await self._repo.save_executive_summary(
            {
                "organization_id": organization_id,
                "period_start": previous[0],
                "period_end": previous[1],
                "summary_text": text,
                "source": source.value,
                "facts_fingerprint": fingerprint(sheet),
                "generated_at": now,
                "finalized_at": now,
            }
        )
        return "finalized"


def _by_name(department: dict) -> str:
    """Sort key: department name, so the same facts always give the same fingerprint."""
    return department["name"]


def _delay_order(delay: dict) -> tuple:
    """Sort key: department then reason, for the same reason."""
    return (delay["department"], delay["reason"])
