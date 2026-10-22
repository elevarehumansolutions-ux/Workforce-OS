"""Business logic for the Scoring module.

Services flush via the repository but never commit: the caller (a request or a
scheduled job) owns the transaction. See 08_DECISIONS.md 2026-10-21 for the
rules implemented here.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.kpis.repository import KPIRepository, KPIScoreRepository
from app.modules.organization.repository import DepartmentRepository
from app.modules.tasks.service import TaskService

from .marking import TaskFacts, count_marks, mark_task, score_from_counts
from .repository import ScoringRepository
from .rollup import weighted_average


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
