"""Business logic for reading saved scores (M12 slice E).

Every read here is behind :class:`PerformanceScope` (``access.py``): anything
the caller may not see is answered "not found", never "forbidden", so nobody
can probe whether a colleague exists or what they scored
(08_DECISIONS.md 2026-10-21, question 8).
"""

import math
import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DepartmentNotFoundException, EmployeeNotFoundException, ValidationException
from app.core.schemas import PaginationMeta
from app.modules.kpis.repository import KPIRepository
from app.modules.organization.models import Employee
from app.modules.organization.repository import DepartmentRepository, EmployeeRepository, PositionRepository
from app.modules.tasks.periods import current_fiscal_quarter
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.repository import OrganizationRepository

from .access import load_performance_scope
from .repository import ScoringRepository
from .rollup import weighted_average
from .schemas import (
    DepartmentPerformanceResponse,
    KPIScoreLine,
    LeaderboardEntry,
    LeaderboardResponse,
    PersonPerformanceResponse,
    PersonScoreLine,
)
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


def _best_first(person: PersonScoreLine) -> tuple:
    """Sort key: highest overall score first, people with no data last, ties by name."""
    has_no_score = person.overall_score is None
    score = person.overall_score if person.overall_score is not None else 0
    return (has_no_score, -score, person.employee_name)


def _leaderboard_order(entry: LeaderboardEntry) -> tuple:
    """Sort key: highest score first, ties by name."""
    return (-entry.overall_score, entry.employee_name)


def _cut_page(items: list, page: int, limit: int) -> tuple[list, PaginationMeta]:
    """One page of an already sorted list, with the same page numbers the other lists use."""
    total = len(items)
    total_pages = math.ceil(total / limit) if total > 0 else 1
    start = (page - 1) * limit
    meta = PaginationMeta(
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )
    return items[start : start + limit], meta


class PerformanceReadService:
    """Reads saved scores for the people the caller is allowed to see."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = ScoringRepository(db)
        self._employee_repo = EmployeeRepository(db)
        self._position_repo = PositionRepository(db)
        self._department_repo = DepartmentRepository(db)
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

    async def _department_kpi_ids(
        self, organization_id: uuid.UUID, department_id: uuid.UUID, last_day: date
    ) -> set[uuid.UUID]:
        """The department's KPIs that count for a period: not deleted, and created by its last day."""
        kpis = await ScoringService._every_item(
            lambda page, limit: self._kpi_repo.list_kpis(organization_id, department_id, None, page, limit)
        )
        return {kpi.id for kpi in kpis if kpi.created_at.date() <= last_day}

    async def _people_lines(
        self,
        department_id: uuid.UUID,
        first_day: date,
        last_day: date,
        kpi_ids: set[uuid.UUID],
    ) -> list[PersonScoreLine]:
        """Every person of the department with their overall score, best first.

        Each person's overall score is worked out here from their saved KPI rows,
        exactly as on their own card. Only rows on the department's KPIs count.
        """
        people = await self._repo.list_people_of_department(department_id, first_day, last_day)
        all_rows = await self._repo.list_scores_for_employees([person.id for person in people], first_day, last_day)

        rows_by_person = {}
        for row in all_rows:
            if row.kpi_id not in kpi_ids:
                continue
            if row.employee_id not in rows_by_person:
                rows_by_person[row.employee_id] = []
            rows_by_person[row.employee_id].append(row)

        lines = []
        for person in people:
            rows = rows_by_person.get(person.id, [])
            pairs = [(row.weight_used, row.score_percentage) for row in rows]
            lines.append(
                PersonScoreLine(
                    employee_id=person.id,
                    employee_name=f"{person.first_name} {person.last_name}",
                    overall_score=weighted_average(pairs),
                    kpis_counted=len([row for row in rows if row.score_percentage is not None]),
                    kpis_expected=len(kpi_ids),
                )
            )
        return sorted(lines, key=_best_first)

    async def _ranked_people(
        self,
        organization_id: uuid.UUID,
        departments: list,
        first_day: date,
        last_day: date,
    ) -> list[LeaderboardEntry]:
        """Everyone in the given departments who has a score, best first, with ranks.

        People with no data are left out (an empty rank is not a rank). Equal
        scores share a rank and the next rank skips, like a race: 1, 2, 2, 4.
        """
        names = {department.id: department.name for department in departments}
        kpi_ids_by_department = {}
        for department in departments:
            kpi_ids_by_department[department.id] = await self._department_kpi_ids(
                organization_id, department.id, last_day
            )

        people = await self._repo.list_people_of_departments(list(names), first_day, last_day)
        all_rows = await self._repo.list_scores_for_employees([person.id for person, _ in people], first_day, last_day)
        rows_by_person = {}
        for row in all_rows:
            rows_by_person.setdefault(row.employee_id, []).append(row)

        scored = []
        for person, department_id in people:
            kpi_ids = kpi_ids_by_department[department_id]
            rows = [row for row in rows_by_person.get(person.id, []) if row.kpi_id in kpi_ids]
            overall = weighted_average([(row.weight_used, row.score_percentage) for row in rows])
            if overall is None:
                continue
            scored.append(
                LeaderboardEntry(
                    rank=0,  # filled in below, once the order is known
                    employee_id=person.id,
                    employee_name=f"{person.first_name} {person.last_name}",
                    department_id=department_id,
                    department_name=names[department_id],
                    overall_score=overall,
                    valid_tasks=sum(row.tasks_on_time + row.tasks_late + row.tasks_not_done for row in rows),
                    kpis_counted=len([row for row in rows if row.score_percentage is not None]),
                    kpis_expected=len(kpi_ids),
                )
            )

        scored.sort(key=_leaderboard_order)
        for position, entry in enumerate(scored):
            if position > 0 and entry.overall_score == scored[position - 1].overall_score:
                entry.rank = scored[position - 1].rank
            else:
                entry.rank = position + 1
        return scored

    async def get_leaderboard(
        self,
        caller: Membership,
        department_id: uuid.UUID | None,
        period_start: date | None,
        period_end: date | None,
        page: int,
        limit: int,
    ) -> LeaderboardResponse:
        """One page of the people ranked by overall score, for the departments the caller may see.

        HR and executives rank the whole company (or one department);
        a head or manager only their own departments. An ordinary employee gets
        "not found": they do not get a list of colleagues' scores.

        Raises:
            EmployeeNotFoundException: The caller may not see a ranked list.
            DepartmentNotFoundException: ``department_id`` does not exist or is not the caller's to see.
            ValidationException: The dates are half given or back to front.
        """
        first_day, last_day = await self._period_for(caller, period_start, period_end)

        scope = await load_performance_scope(self._db, caller)
        if not scope.can_see_ranked_list():
            raise EmployeeNotFoundException()

        if department_id is not None:
            department = await self._department_repo.get_department_by_id(department_id)
            if department is None or not scope.can_see_department(department.id):
                raise DepartmentNotFoundException()
            departments = [department]
        elif scope.sees_all:
            departments = await ScoringService._every_item(
                lambda page_number, size: self._department_repo.list_departments(
                    caller.organization_id, page_number, size
                )
            )
        else:
            departments = []
            for visible_id in scope.department_ids:
                visible = await self._department_repo.get_department_by_id(visible_id)
                if visible is not None:
                    departments.append(visible)

        ranked = await self._ranked_people(caller.organization_id, departments, first_day, last_day)
        entries, pagination = _cut_page(ranked, page, limit)
        is_final = await self._repo.period_is_frozen(caller.organization_id, first_day, last_day)
        return LeaderboardResponse(
            period_start=first_day,
            period_end=last_day,
            is_final=is_final,
            entries=entries,
            pagination=pagination,
        )

    async def get_department_performance(
        self,
        caller: Membership,
        department_id: uuid.UUID,
        period_start: date | None,
        period_end: date | None,
        page: int,
        limit: int,
    ) -> DepartmentPerformanceResponse:
        """A department's two numbers for a period, and one page of its people.

        Raises:
            DepartmentNotFoundException: No such department, or the caller may not see it.
            ValidationException: The dates are half given or back to front.
        """
        first_day, last_day = await self._period_for(caller, period_start, period_end)

        scope = await load_performance_scope(self._db, caller)
        department = await self._department_repo.get_department_by_id(department_id)
        if department is None or not scope.can_see_department(department.id):
            raise DepartmentNotFoundException()

        saved = await self._repo.get_department_score(department.id, first_day, last_day)
        kpi_ids = await self._department_kpi_ids(caller.organization_id, department.id, last_day)
        people = await self._people_lines(department.id, first_day, last_day, kpi_ids)
        one_page, pagination = _cut_page(people, page, limit)

        # Say why a number is empty, so the screen can show "no data yet" with a reason, never a 0.
        kpi_reason = None
        punctuality_reason = None
        if saved is None:
            kpi_reason = "No scores have been worked out for this period yet."
            punctuality_reason = kpi_reason
        else:
            if saved.kpi_results_score is None:
                if saved.kpis_expected == 0:
                    kpi_reason = "This department has no KPIs in this period."
                else:
                    kpi_reason = "No KPI of this department has a result yet."
            if saved.punctuality_score is None:
                punctuality_reason = "No task of this department had a deadline in this period."

        return DepartmentPerformanceResponse(
            department_id=department.id,
            department_name=department.name,
            period_start=first_day,
            period_end=last_day,
            is_final=saved is not None and saved.finalized_at is not None,
            kpi_results_score=saved.kpi_results_score if saved else None,
            kpis_counted=saved.kpis_counted if saved else 0,
            kpis_expected=saved.kpis_expected if saved else len(kpi_ids),
            kpi_results_no_data_reason=kpi_reason,
            punctuality_score=saved.punctuality_score if saved else None,
            punctuality_on_time=saved.punctuality_on_time if saved else 0,
            punctuality_late=saved.punctuality_late if saved else 0,
            punctuality_not_done=saved.punctuality_not_done if saved else 0,
            punctuality_no_data_reason=punctuality_reason,
            people=one_page,
            people_pagination=pagination,
        )
