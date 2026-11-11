"""Business logic for the Scoring module.

Services flush via the repository but never commit: the caller (a request or a
scheduled job) owns the transaction. See 08_DECISIONS.md 2026-10-21 for the
rules implemented here.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.kpis.enums import KPITrackingMode
from app.modules.kpis.repository import KPIRepository, KPIScoreRepository
from app.modules.kpis.service import KPIService
from app.modules.organization.repository import DepartmentRepository
from app.modules.tasks.periods import current_fiscal_quarter
from app.modules.tasks.service import TaskService
from app.modules.tenancy_identity.repository import OrganizationRepository

from .marking import TaskFacts, count_marks, mark_task, score_from_counts
from .repository import ScoringRepository
from .rollup import weighted_average
from .weight_check import KpiWeightCheck


# The most ``kpi_scores.score_percentage`` can hold (a DECIMAL(5,2) column).
KPI_SCORE_MAX = Decimal("999.99")


def period_dates(period_start: datetime, period_end: datetime) -> tuple[date, date]:
    """The first and last DAY of a period, from its first moment and the moment after it.

    Example: a quarter from 1 July 00:00 up to (not including) 1 October 00:00 is
    1 July to 30 September. The datetimes are on the organization's clock, so
    ``.date()`` gives the organization's own calendar day.
    """
    return period_start.date(), (period_end - timedelta(days=1)).date()


class ScoringService:
    """Business logic for working out and saving scores."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = ScoringRepository(db)
        self._task_service = TaskService(db)
        self._kpi_repo = KPIRepository(db)
        self._kpi_score_repo = KPIScoreRepository(db)
        self._department_repo = DepartmentRepository(db)
        self._organization_repo = OrganizationRepository(db)

    async def run_nightly(self, organization_id: uuid.UUID, now: datetime) -> dict:
        """One organization's nightly scoring: close last quarter once, refresh this one.

        1. If the PREVIOUS fiscal quarter is not closed yet, and the organization
           already existed when it ended, close it: write the final task-count KPI
           results, the final person and department scores, and freeze them. A
           second run finds it frozen and skips it, and a late run gives the same
           numbers (everything is judged at the quarter's end).
        2. Refresh the CURRENT quarter's "so far" rows.

        The caller sets the tenant context and owns the transaction, so an
        organization's whole night is saved together or not at all.

        Args:
            organization_id: The organization.
            now: The current moment (any timezone).

        Returns:
            ``{"closed_previous_period": bool}``, for logging.
        """
        organization = await self._organization_repo.get_organization_by_id(organization_id)
        if organization is None:
            return {"closed_previous_period": False}

        month, timezone_name = organization.fiscal_year_start_month, organization.timezone
        current_start, current_end = current_fiscal_quarter(month, timezone_name, now)
        previous_start, previous_end = current_fiscal_quarter(
            month, timezone_name, current_start - timedelta(seconds=1)
        )

        closed_previous_period = False
        first_day, last_day = period_dates(previous_start, previous_end)
        existed_then = organization.created_at < previous_end  # no empty frozen quarters before it began
        if existed_then and not await self._repo.period_is_frozen(organization_id, first_day, last_day):
            await self.close_period(organization_id, previous_start, previous_end, now)
            closed_previous_period = True

        await self.refresh_open_period(organization_id, current_start, current_end, now)

        # A reminder, never a block: scoring above already ran on the weights that exist. Only
        # for a company that already existed when this quarter began (a brand-new one is still
        # drafting; the KPIs screen warns it ahead of its first quarter).
        if organization.created_at < current_start:
            await KpiWeightCheck(self._db).run(organization_id, current_start)
        return {"closed_previous_period": closed_previous_period}

    async def refresh_open_period(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> None:
        """Refresh the "so far" rows of a period that is still open (nothing is frozen)."""
        await self.save_task_count_results(organization_id, period_start, period_end)
        await self.compute_employee_scores(organization_id, period_start, period_end, now)
        await self.compute_department_scores(organization_id, period_start, period_end, now)

    async def close_period(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> None:
        """Write the final numbers of a period that has ended, then freeze them.

        The task-count KPI results come first because the department headline
        reads them. ``now`` must be at or after ``period_end``.
        """
        await self.save_task_count_results(organization_id, period_start, period_end)
        await self.finalize_employee_scores(organization_id, period_start, period_end, now)
        await self.finalize_department_scores(organization_id, period_start, period_end, now)

    async def save_task_count_results(
        self, organization_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> int:
        """Save the result of every task-count KPI for a period, in ``kpi_scores``.

        A task-count KPI's number is the count of tasks linked to it that were
        completed in the period, turned into a percentage of its target by the
        KPI module's own rule. Typed-in KPIs are not touched (HR enters those).
        The percentage is capped at 999.99, the most ``kpi_scores`` can hold, so
        a KPI far above its target cannot make a whole night fail. These rows go
        through the KPI score repository because the typed-in path refuses
        task-count KPIs (``KPI_TRACKED_BY_TASKS``).

        Returns:
            How many task-count KPI results were written.
        """
        first_day, last_day = period_dates(period_start, period_end)
        kpis = await self._every_item(
            lambda page, limit: self._kpi_repo.list_kpis(organization_id, None, None, page, limit)
        )

        written = 0
        for kpi in kpis:
            if kpi.tracking_mode != KPITrackingMode.TASK_COUNT.value:
                continue
            completed = await self._task_service.count_completed_tasks_for_kpi(kpi.id, period_start, period_end)
            actual = Decimal(completed)
            percentage = KPIService.calculate_score_percentage(actual, kpi.target_value, kpi.is_inverse)
            if percentage is not None:
                percentage = min(percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), KPI_SCORE_MAX)

            values = {"actual_value": actual, "score_percentage": percentage}
            saved = await self._kpi_score_repo.get_score_for_period(kpi.id, first_day, last_day)
            if saved is None:
                await self._kpi_score_repo.create_kpi_score(
                    {
                        "organization_id": organization_id,
                        "kpi_id": kpi.id,
                        "period_start": first_day,
                        "period_end": last_day,
                        **values,
                    }
                )
            else:
                await self._kpi_score_repo.update_score(saved, values)
            written += 1
        return written

    async def compute_employee_scores(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> int:
        """Work out and save every person's score on every KPI for one period.

        Each valid task a person holds at the end earns 100 (on time), 50 (late)
        or 0 (not done); the score on a KPI is the average. Tasks nobody holds
        and tasks with no KPI link are not part of a person's score. A running
        row is refreshed; a frozen row is left alone. A running row whose tasks
        have disappeared is reset to "no tasks".

        Args:
            organization_id: The organization.
            period_start: The first moment of the period (the organization's clock).
            period_end: The first moment AFTER the period.
            now: The moment we are judging at (a period's own end for the final write).

        Returns:
            How many rows were written or refreshed.
        """
        marks_by_person_and_kpi = await self._marks_by_person_and_kpi(period_start, period_end, now)
        first_day, last_day = period_dates(period_start, period_end)

        saved_rows = 0
        saved_keys = set()
        kpis = {}  # a KPI is looked up once, however many people have tasks on it
        for (employee_id, kpi_id), marks in marks_by_person_and_kpi.items():
            if kpi_id not in kpis:
                kpis[kpi_id] = await self._kpi_repo.get_kpi_by_id(kpi_id)
            kpi = kpis[kpi_id]
            if kpi is None:
                continue  # the KPI was deleted: nothing to score against

            on_time, late, not_done = count_marks(marks)
            row = await self._repo.save_employee_score(
                {
                    "organization_id": organization_id,
                    "employee_id": employee_id,
                    "kpi_id": kpi_id,
                    "period_start": first_day,
                    "period_end": last_day,
                    "tasks_on_time": on_time,
                    "tasks_late": late,
                    "tasks_not_done": not_done,
                    "score_percentage": score_from_counts(on_time, late, not_done),
                    "weight_used": kpi.weight,
                }
            )
            saved_keys.add((employee_id, kpi_id))
            if row is not None:
                saved_rows += 1

        # A running row for a person and KPI that no longer has any valid task.
        for row in await self._repo.list_running_employee_scores(organization_id, first_day, last_day):
            if (row.employee_id, row.kpi_id) not in saved_keys:
                await self._repo.clear_running_employee_score(row.id)
        return saved_rows

    async def finalize_employee_scores(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> int:
        """Write the final person scores of a period that has closed, then freeze them.

        ``now`` must be at or after ``period_end``. Work finished after the
        period's end does not count in it (see ``mark_task``).

        Returns:
            How many rows were frozen.
        """
        await self.compute_employee_scores(organization_id, period_start, period_end, now)
        first_day, last_day = period_dates(period_start, period_end)
        return await self._repo.finalize_employee_scores(organization_id, first_day, last_day, now)

    async def compute_department_scores(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> int:
        """Work out and save every department's two numbers for one period.

        The two numbers are kept apart and never blended (08_DECISIONS.md
        2026-10-21, question 5): the KPI RESULTS (the weighted results the
        department's KPIs have saved for this period; a KPI with no saved
        result is left out and the weights are rescaled) and the TEAM
        PUNCTUALITY (the 100 / 50 / 0 marking over ALL the department's tasks
        with a real deadline in the period, including tasks nobody holds and
        tasks with no KPI link). Every department gets a row, even with no data,
        so the history is complete. A frozen row is left alone.

        Returns:
            How many rows were written or refreshed.
        """
        first_day, last_day = period_dates(period_start, period_end)
        punctuality = await self._counts_by_department(period_start, period_end, now)
        departments = await self._every_item(
            lambda page, limit: self._department_repo.list_departments(organization_id, page, limit)
        )

        saved_rows = 0
        for department in departments:
            kpis = await self._every_item(
                lambda page, limit: self._kpi_repo.list_kpis(organization_id, department.id, None, page, limit)
            )
            results = []  # (weight, saved result or None) for each of the department's KPIs
            for kpi in kpis:
                saved = await self._kpi_score_repo.get_score_for_period(kpi.id, first_day, last_day)
                results.append((kpi.weight, saved.score_percentage if saved is not None else None))

            on_time, late, not_done = punctuality.get(department.id, (0, 0, 0))
            row = await self._repo.save_department_score(
                {
                    "organization_id": organization_id,
                    "department_id": department.id,
                    "period_start": first_day,
                    "period_end": last_day,
                    "kpi_results_score": weighted_average(results),
                    "kpis_counted": len([pair for pair in results if pair[1] is not None]),
                    "kpis_expected": len(kpis),
                    "punctuality_on_time": on_time,
                    "punctuality_late": late,
                    "punctuality_not_done": not_done,
                    "punctuality_score": score_from_counts(on_time, late, not_done),
                    "revenue_allocation_percentage": department.revenue_allocation_percentage,
                }
            )
            if row is not None:
                saved_rows += 1
        return saved_rows

    async def finalize_department_scores(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> int:
        """Write the final department scores of a period that has closed, then freeze them.

        ``now`` must be at or after ``period_end``.

        Returns:
            How many rows were frozen.
        """
        await self.compute_department_scores(organization_id, period_start, period_end, now)
        first_day, last_day = period_dates(period_start, period_end)
        return await self._repo.finalize_department_scores(organization_id, first_day, last_day, now)

    async def _counts_by_department(
        self, period_start: datetime, period_end: datetime, now: datetime
    ) -> dict:
        """Mark ALL the period's tasks and count the marks per department."""
        rows = await self._task_service.list_tasks_for_scoring(period_start, period_end)
        marks_by_department = {}
        for row in rows:
            facts = TaskFacts(
                status=row.status,
                due_at=row.due_at,
                completed_at=row.completed_at,
                approved_blocked_seconds=row.approved_blocked_seconds,
                has_pending_block=row.has_pending_block,
                last_block_reviewed_at=row.last_block_reviewed_at,
            )
            mark = mark_task(facts, period_start, period_end, now)
            if mark is not None:
                marks_by_department.setdefault(row.department_id, []).append(mark)
        return {department_id: count_marks(marks) for department_id, marks in marks_by_department.items()}

    async def live_counts_by_department(self, period_start: datetime, period_end: datetime, now: datetime) -> dict:
        """On-time, late and not-done counts per department for any window, marked right now.

        Used by the custom date range, which is worked out live instead of read
        from the saved quarters. Same marking as the nightly job.

        Returns:
            ``{department_id: (on_time, late, not_done)}``; departments with no valid task are absent.
        """
        return await self._counts_by_department(period_start, period_end, now)

    @staticmethod
    async def _every_item(fetch_page) -> list:
        """Collect every item of a paginated list, page after page.

        ``fetch_page(page, limit)`` returns one page (the repositories'
        ``PaginationResponse``). A page of 100 keeps the number of queries small.
        """
        items = []
        page = 1
        while True:
            result = await fetch_page(page, 100)
            items.extend(result.data)
            if not result.pagination.has_next:
                return items
            page += 1

    async def _marks_by_person_and_kpi(
        self, period_start: datetime, period_end: datetime, now: datetime
    ) -> dict:
        """Mark the period's tasks and group the marks by (person, KPI)."""
        rows = await self._task_service.list_tasks_for_scoring(period_start, period_end)
        groups = {}
        for row in rows:
            if row.assigned_to_employee_id is None or row.kpi_id is None:
                continue  # nobody holds it, or it counts toward no KPI: not part of a person's score
            facts = TaskFacts(
                status=row.status,
                due_at=row.due_at,
                completed_at=row.completed_at,
                approved_blocked_seconds=row.approved_blocked_seconds,
                has_pending_block=row.has_pending_block,
                last_block_reviewed_at=row.last_block_reviewed_at,
            )
            mark = mark_task(facts, period_start, period_end, now)
            if mark is None:
                continue
            key = (row.assigned_to_employee_id, row.kpi_id)
            groups.setdefault(key, []).append(mark)
        return groups
