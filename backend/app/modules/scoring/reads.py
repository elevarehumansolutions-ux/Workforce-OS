"""Business logic for reading saved scores (M12 slice E).

Every read here is behind :class:`PerformanceScope` (``access.py``): anything
the caller may not see is answered "not found", never "forbidden", so nobody
can probe whether a colleague exists or what they scored
(08_DECISIONS.md 2026-10-21, question 8).
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmployeeNotFoundException, ValidationException
from app.modules.kpis.repository import KPIRepository
from app.modules.organization.models import Employee
from app.modules.organization.repository import EmployeeRepository, PositionRepository
from app.modules.tasks.periods import current_fiscal_quarter
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.repository import OrganizationRepository

from .access import load_performance_scope
from .repository import ScoringRepository
from .rollup import weighted_average
from .schemas import KPIScoreLine, PersonPerformanceResponse
from .service import ScoringService, period_dates


def resolve_period(
    fiscal_year_start_month: int,
    timezone_name: str,
    now: datetime,
    period_start: date | None,
    period_end: date | None,
) -> tuple[date, date]:
    """The first and last day a read is about.

    With no dates given, it is the organization's current fiscal quarter.
    Otherwise the two dates are used exactly as given: they are matched against
    the saved periods, so a pair that matches none simply has no data.

    Args:
        fiscal_year_start_month: The organization's fiscal year start month (1-12).
        timezone_name: The organization's IANA timezone.
        now: The current moment.
        period_start: First day asked for, or ``None``.
        period_end: Last day asked for, or ``None``.

    Raises:
        ValidationException: Only one of the two dates was given, or the end
            is before the start.
    """
    if period_start is None and period_end is None:
        start, end = current_fiscal_quarter(fiscal_year_start_month, timezone_name, now)
        return period_dates(start, end)

    if period_start is None or period_end is None:
        raise ValidationException("Give both period_start and period_end, or neither.")
    if period_end < period_start:
        raise ValidationException("period_end cannot be before period_start.")
    return period_start, period_end


def _heaviest_first(line: KPIScoreLine) -> tuple:
    """Sort key: the KPI that counts most first, ties by name."""
    return (-line.weight, line.kpi_name)


class PerformanceReadService:
    """Reads saved scores for the people the caller is allowed to see."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = ScoringRepository(db)
        self._employee_repo = EmployeeRepository(db)
        self._position_repo = PositionRepository(db)
        self._kpi_repo = KPIRepository(db)
        self._organization_repo = OrganizationRepository(db)

    async def _period_for(
        self, caller: Membership, period_start: date | None, period_end: date | None
    ) -> tuple[date, date]:
        """The period a read is about, on the caller's organization's own calendar."""
        organization = await self._organization_repo.get_organization_by_id(caller.organization_id)
        return resolve_period(
            organization.fiscal_year_start_month,
            organization.timezone,
            datetime.now(UTC),
            period_start,
            period_end,
        )

    async def _find_visible_person(
        self, caller: Membership, employee_id: uuid.UUID | None
    ) -> tuple[Employee, uuid.UUID | None]:
        """The person asked for and their department, or "not found" if the caller may not see them.

        ``employee_id=None`` means "me". A person the caller may not see looks
        exactly like a person who does not exist (08_DECISIONS.md, question 8).

        Raises:
            EmployeeNotFoundException: No such person, or not visible to the caller.
        """
        scope = await load_performance_scope(self._db, caller)

        if employee_id is None:
            employee_id = scope.employee_id
        if employee_id is None:
            raise EmployeeNotFoundException()  # "me", but the caller has no employee record

        employee = await self._employee_repo.get_employee_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundException()

        department_id = None
        position = await self._position_repo.get_position_by_id(employee.position_id)
        if position is not None:
            department_id = position.department_id

        if not scope.can_see_person(employee.id, department_id):
            raise EmployeeNotFoundException()
        return employee, department_id

    async def _build_lines(
        self,
        organization_id: uuid.UUID,
        department_id: uuid.UUID | None,
        last_day: date,
        rows: list,
    ) -> list[KPIScoreLine]:
        """One line per KPI: the saved result, or "no data" for a department KPI with no row.

        The weight shown for a saved row is the weight it was scored with
        (``weight_used``), so a closed period still reads the way it was
        published even if HR changed the weights later. A KPI created after the
        period ended is not listed as missing data for it, and a deleted KPI is
        left out.
        """
        lines = []
        listed = set()

        for row in rows:
            kpi = await self._kpi_repo.get_kpi_by_id(row.kpi_id)
            if kpi is None:
                continue
            lines.append(
                KPIScoreLine(
                    kpi_id=row.kpi_id,
                    kpi_name=kpi.name,
                    weight=row.weight_used,
                    score_percentage=row.score_percentage,
                    tasks_on_time=row.tasks_on_time,
                    tasks_late=row.tasks_late,
                    tasks_not_done=row.tasks_not_done,
                )
            )
            listed.add(row.kpi_id)

        if department_id is not None:
            department_kpis = await ScoringService._every_item(
                lambda page, limit: self._kpi_repo.list_kpis(organization_id, department_id, None, page, limit)
            )
            for kpi in department_kpis:
                if kpi.id in listed or kpi.created_at.date() > last_day:
                    continue
                lines.append(
                    KPIScoreLine(
                        kpi_id=kpi.id,
                        kpi_name=kpi.name,
                        weight=kpi.weight,
                        score_percentage=None,
                        tasks_on_time=0,
                        tasks_late=0,
                        tasks_not_done=0,
                    )
                )

        return sorted(lines, key=_heaviest_first)

    async def get_person_performance(
        self,
        caller: Membership,
        employee_id: uuid.UUID | None,
        period_start: date | None,
        period_end: date | None,
    ) -> PersonPerformanceResponse:
        """A person's performance card for one period (``employee_id=None`` means the caller).

        The overall score is worked out here from the saved per-KPI rows, with
        the weights those rows were scored with, so it never needs its own
        stored copy that could drift from them.

        Raises:
            EmployeeNotFoundException: No such person, or the caller may not see them.
            ValidationException: The dates are half given or back to front.
        """
        first_day, last_day = await self._period_for(caller, period_start, period_end)
        employee, department_id = await self._find_visible_person(caller, employee_id)

        rows = await self._repo.list_scores_for_employee(employee.id, first_day, last_day)
        lines = await self._build_lines(caller.organization_id, department_id, last_day, rows)

        pairs = [(line.weight, line.score_percentage) for line in lines]
        overall_score = weighted_average(pairs)
        kpis_counted = len([line for line in lines if line.score_percentage is not None])

        no_data_reason = None
        if overall_score is None:
            if len(lines) == 0:
                no_data_reason = "This person's department had no KPIs in this period."
            else:
                no_data_reason = "No tasks linked to a KPI were assigned to this person in this period."

        # Final means: there are saved rows and every one of them is frozen.
        is_final = len(rows) > 0 and all(row.finalized_at is not None for row in rows)

        return PersonPerformanceResponse(
            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            department_id=department_id,
            period_start=first_day,
            period_end=last_day,
            is_final=is_final,
            overall_score=overall_score,
            kpis_counted=kpis_counted,
            kpis_expected=len(lines),
            no_data_reason=no_data_reason,
            kpis=lines,
        )
