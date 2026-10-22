"""Data-access layer for the Scoring module.

Every method works inside the caller's RLS-scoped session and only flushes,
never commits: the caller (a request or a scheduled job) owns the transaction.

Writing a row never touches a FROZEN row (one whose ``finalized_at`` is set):
the rules below only act on rows whose ``finalized_at`` is empty, in a single
atomic statement, so two jobs running at once cannot unfreeze or rewrite a
closed period. (The database also refuses such a change with a trigger, as a
second layer; see 04_DATABASE.md.)
"""

import uuid
from datetime import date, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DepartmentScore, EmployeeKPIScore


class ScoringRepository:
    """Handles persistence for the saved scores."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def list_organizations_needing_scoring(self) -> list[uuid.UUID]:
        """The ids of the organizations the nightly scoring job should work on.

        The one cross-tenant read of this module, and the job's only way to find
        which organizations to look at: with no tenant context set, RLS returns
        nothing. It calls the ``SECURITY DEFINER`` function
        ``organizations_needing_scoring()`` (see its migration), which reveals
        only organization ids, and only for organizations that have a KPI or a
        task with a deadline.

        Returns:
            The ids of the organizations to score.
        """
        result = await self._db.execute(text("SELECT organization_id FROM organizations_needing_scoring()"))
        return [row.organization_id for row in result]

    async def period_is_frozen(
        self, organization_id: uuid.UUID, period_start: date, period_end: date
    ) -> bool:
        """Whether a period has already been closed for an organization.

        Every department gets a row on every run, so a period counts as closed
        once any of its department rows is frozen. The nightly job uses this to
        close a period exactly once: a second run finds it frozen and skips it.

        Args:
            organization_id: The organization.
            period_start: First day of the period.
            period_end: Last day of the period.
        """
        stmt = (
            select(func.count())
            .select_from(DepartmentScore)
            .where(
                DepartmentScore.organization_id == organization_id,
                DepartmentScore.period_start == period_start,
                DepartmentScore.period_end == period_end,
                DepartmentScore.finalized_at.is_not(None),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one() > 0

    async def save_employee_score(self, fields: dict) -> EmployeeKPIScore | None:
        """Insert a person's score row, or refresh the running one for the same period.

        One row exists per person, KPI and period. If it exists and is still
        running, its counts, score and weight are replaced. If it is already
        frozen, nothing is changed.

        Args:
            fields: The row's values: ``organization_id``, ``employee_id``,
                ``kpi_id``, ``period_start``, ``period_end``, the three counts,
                ``score_percentage`` and ``weight_used``.

        Returns:
            The saved row, or ``None`` if the row was frozen and left alone.
        """
        stmt = insert(EmployeeKPIScore).values(**fields)
        refreshed = {
            name: stmt.excluded[name]
            for name in (
                "tasks_on_time",
                "tasks_late",
                "tasks_not_done",
                "score_percentage",
                "weight_used",
            )
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_employee_kpi_scores_one_per_period",
            set_={**refreshed, "updated_at": func.now()},
            where=EmployeeKPIScore.finalized_at.is_(None),  # a frozen row is never rewritten
        ).returning(EmployeeKPIScore)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_running_employee_scores(
        self, organization_id: uuid.UUID, period_start: date, period_end: date
    ) -> list[EmployeeKPIScore]:
        """The not-yet-frozen person scores of one period.

        Args:
            organization_id: The organization.
            period_start: First day of the period.
            period_end: Last day of the period.
        """
        stmt = select(EmployeeKPIScore).where(
            EmployeeKPIScore.organization_id == organization_id,
            EmployeeKPIScore.period_start == period_start,
            EmployeeKPIScore.period_end == period_end,
            EmployeeKPIScore.finalized_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_scores_for_employee(
        self, employee_id: uuid.UUID, period_start: date, period_end: date
    ) -> list[EmployeeKPIScore]:
        """One person's saved KPI rows for one period, running or frozen.

        Read as they are in the database (``populate_existing``) so a row the
        nightly job just refreshed in this same session is not served stale.

        Args:
            employee_id: The person.
            period_start: First day of the period.
            period_end: Last day of the period.
        """
        stmt = (
            select(EmployeeKPIScore)
            .where(
                EmployeeKPIScore.employee_id == employee_id,
                EmployeeKPIScore.period_start == period_start,
                EmployeeKPIScore.period_end == period_end,
            )
            .execution_options(populate_existing=True)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def clear_running_employee_score(self, score_id: uuid.UUID) -> None:
        """Reset a running row to "no tasks": zero counts and an empty score.

        Used when a person no longer has any valid task on that KPI in the
        period (for example the task was cancelled), so a stale number does not
        linger. A frozen row is never touched.
        """
        stmt = (
            update(EmployeeKPIScore)
            .where(EmployeeKPIScore.id == score_id, EmployeeKPIScore.finalized_at.is_(None))
            .values(tasks_on_time=0, tasks_late=0, tasks_not_done=0, score_percentage=None)
        )
        await self._db.execute(stmt)

    async def save_department_score(self, fields: dict) -> DepartmentScore | None:
        """Insert a department's row, or refresh the running one for the same period.

        One row exists per department and period. If it exists and is still
        running, its numbers are replaced. If it is already frozen, nothing is
        changed (the same atomic guard as ``save_employee_score``).

        Args:
            fields: The row's values: ``organization_id``, ``department_id``,
                ``period_start``, ``period_end``, ``kpi_results_score``,
                ``kpis_counted``, ``kpis_expected``, the three ``punctuality_``
                counts, ``punctuality_score`` and ``revenue_allocation_percentage``.

        Returns:
            The saved row, or ``None`` if the row was frozen and left alone.
        """
        stmt = insert(DepartmentScore).values(**fields)
        refreshed = {
            name: stmt.excluded[name]
            for name in (
                "kpi_results_score",
                "kpis_counted",
                "kpis_expected",
                "punctuality_on_time",
                "punctuality_late",
                "punctuality_not_done",
                "punctuality_score",
                "revenue_allocation_percentage",
            )
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_department_scores_one_per_period",
            set_={**refreshed, "updated_at": func.now()},
            where=DepartmentScore.finalized_at.is_(None),  # a frozen row is never rewritten
        ).returning(DepartmentScore)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def finalize_department_scores(
        self, organization_id: uuid.UUID, period_start: date, period_end: date, now: datetime
    ) -> int:
        """Freeze every running department score of the period at ``now``.

        Returns:
            How many rows were frozen.
        """
        stmt = (
            update(DepartmentScore)
            .where(
                DepartmentScore.organization_id == organization_id,
                DepartmentScore.period_start == period_start,
                DepartmentScore.period_end == period_end,
                DepartmentScore.finalized_at.is_(None),
            )
            .values(finalized_at=now)
        )
        result = await self._db.execute(stmt)
        return result.rowcount

    async def finalize_employee_scores(
        self, organization_id: uuid.UUID, period_start: date, period_end: date, now: datetime
    ) -> int:
        """Freeze every running person score of the period at ``now``.

        Returns:
            How many rows were frozen.
        """
        stmt = (
            update(EmployeeKPIScore)
            .where(
                EmployeeKPIScore.organization_id == organization_id,
                EmployeeKPIScore.period_start == period_start,
                EmployeeKPIScore.period_end == period_end,
                EmployeeKPIScore.finalized_at.is_(None),
            )
            .values(finalized_at=now)
        )
        result = await self._db.execute(stmt)
        return result.rowcount
