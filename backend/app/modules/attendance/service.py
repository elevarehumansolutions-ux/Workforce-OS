"""Business logic for the attendance module.

Wraps :class:`AttendanceRepository` with the rules the database alone can't
express: who is allowed to clock in, that a repeat clock-in is a harmless
retry, and recovering when two simultaneous clock-ins race. Services flush
via the repository but never commit; the router commits after a successful
call.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EmployeeNotFoundException,
    NoEmployeeProfileException,
    NotClockedInException,
    PermissionDeniedException,
    ValidationException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.service import AuditService, NotificationService
from app.modules.organization.enums import EmployeeStatus
from app.modules.organization.repository import EmployeeRepository
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.repository import OrganizationRepository

from .enums import AttendanceClosedBy
from .models import AttendanceRecord
from .repository import AttendanceRepository


_HISTORY_VIEWER_ROLES = {"hr_administrator", "business_executive"}

_AUTO_CLOSE_REASON = "Did not clock out"


def _local_day_window(
    timezone_name: str, date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """Turn calendar dates into the exact moments that bound them in an org's timezone.

    A date means a day on the organization's wall clock, not in UTC: for a
    Lagos org, a 00:30 clock-in on 2 October is 23:30 UTC on 1 October, and
    must still be found by a filter for 2 October. The end is exclusive (the
    start of the day after ``date_to``), so ``date_to`` is inclusive.

    Args:
        timezone_name: The organization's IANA timezone name.
        date_from: First day to include, or ``None`` for no lower bound.
        date_to: Last day to include, or ``None`` for no upper bound.

    Returns:
        ``(start, end_exclusive)`` as timezone-aware datetimes, either of
        which may be ``None``.
    """
    tz = ZoneInfo(timezone_name)
    start = datetime.combine(date_from, time.min, tzinfo=tz) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz) if date_to else None
    return start, end


class AttendanceService:
    """Business logic for clocking in and out, and reading attendance history."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = AttendanceRepository(db)
        self._employee_repo = EmployeeRepository(db)
        self._org_repo = OrganizationRepository(db)
        self._audit = AuditService(db)
        self._notifications = NotificationService(db)

    async def list_history(
        self,
        caller: Membership,
        employee_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List an employee's attendance history, newest first.

        With no ``employee_id`` it is the caller's own history. HR
        administrators and business executives may pass any employee in the
        organization; everyone else may only ask for themselves. Dates are
        calendar days on the organization's wall clock (its timezone).

        Args:
            caller: The acting membership (supplies user, org and role).
            employee_id: Whose history to read; ``None`` means the caller's own.
            date_from: First day to include.
            date_to: Last day to include.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response of ``AttendanceRecord`` rows.

        Raises:
            ValidationException: If ``date_from`` is after ``date_to``.
            NoEmployeeProfileException: If asking for their own history
                without having an employee record.
            PermissionDeniedException: If a role without access asks for
                someone else's history.
            EmployeeNotFoundException: If ``employee_id`` is not an
                employee of this organization.
        """
        if date_from and date_to and date_from > date_to:
            raise ValidationException(message="date_from must not be after date_to")

        own = await self._employee_repo.get_employee_by_user_id(caller.user_id)
        if employee_id is None:
            # "Show my history": needs an employee record of my own.
            if own is None:
                raise NoEmployeeProfileException()
            target_id = own.id
        elif own is not None and employee_id == own.id:
            # I passed my own id: the same as asking for my own history.
            target_id = own.id
        else:
            # Someone else's history: my role decides, my own record is irrelevant.
            if caller.role not in _HISTORY_VIEWER_ROLES:
                raise PermissionDeniedException("You can only view your own attendance")
            target = await self._employee_repo.get_employee_by_id(employee_id)
            if target is None:
                raise EmployeeNotFoundException()
            target_id = target.id

        organization = await self._org_repo.get_organization_by_id(caller.organization_id)
        start, end = _local_day_window(organization.timezone, date_from, date_to)
        return await self._repo.list_records(target_id, start, end, page, limit)

    async def clock_in(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> tuple[AttendanceRecord, bool]:
        """Clock the caller in, or return the record they are already clocked in on.

        Attendance belongs to the employee record, not the role: the caller
        is matched to their employee through ``employees.user_id``. Clocking
        in twice is a harmless retry, not an error: the second call returns
        the open record with ``already_clocked_in=True``, so a client can
        tell "you just clocked in" from "you already were".

        There is no "look first, then insert" step to race against: the
        insert itself is ``ON CONFLICT DO NOTHING`` on the one-open-record
        index, so the database settles two simultaneous clock-ins in one
        atomic statement. The winner gets a new record back; the loser (and
        any plain repeat tap) gets nothing back and reads the open record
        that is already there.

        Args:
            user_id: The logged-in user clocking in.
            organization_id: The user's current organization.

        Returns:
            ``(record, already_clocked_in)``: the open record, and whether it
            already existed before this call.

        Raises:
            NoEmployeeProfileException: If the user has no employee record
                in this organization.
            ValidationException: If the employee has been offboarded.
        """
        employee = await self._employee_repo.get_employee_by_user_id(user_id)
        if employee is None:
            raise NoEmployeeProfileException()
        if employee.status == EmployeeStatus.INACTIVE.value:
            raise ValidationException(message="Offboarded employees cannot clock in")

        now = datetime.now(UTC)
        record = await self._repo.create_open_record(organization_id, employee.id, now)
        if record is None:
            # Already clocked in: a repeat tap, or we lost a simultaneous race.
            return await self._repo.get_open_record(employee.id), True

        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=user_id,
            action="clock_in",
            entity_type="attendance_record",
            entity_id=record.id,
            changes={
                "old": None,
                "new": {"employee_id": str(employee.id), "clock_in_at": now.isoformat()},
            },
        )
        return record, False

    async def clock_out(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> AttendanceRecord:
        """Clock the caller out of their open record.

        Unlike clocking in, this is not idempotent: with no open record
        there is nothing to close and no clock-out time to report, and a
        silent success could hide a client showing the wrong state. The
        close is one atomic conditional UPDATE, so two simultaneous
        clock-outs can't both succeed: one closes the record, the other gets
        ``NotClockedInException``, and the first clock-out time stands.

        Args:
            user_id: The logged-in user clocking out.
            organization_id: The user's current organization.

        Returns:
            The closed ``AttendanceRecord``.

        Raises:
            NoEmployeeProfileException: If the user has no employee record
                in this organization.
            NotClockedInException: If the employee has no open record.
        """
        employee = await self._employee_repo.get_employee_by_user_id(user_id)
        if employee is None:
            raise NoEmployeeProfileException()

        now = datetime.now(UTC)
        record = await self._repo.close_open_record(employee.id, now, AttendanceClosedBy.EMPLOYEE)
        if record is None:
            raise NotClockedInException()

        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=user_id,
            action="clock_out",
            entity_type="attendance_record",
            entity_id=record.id,
            changes={
                "old": {"clock_out_at": None},
                "new": {"clock_out_at": record.clock_out_at.isoformat(), "closed_by": record.closed_by},
            },
        )
        return record

    async def auto_close_stale_records(
        self, organization_id: uuid.UUID, now: datetime | None = None
    ) -> int:
        """Close everyone still clocked in from before this organization's last midnight.

        The nightly safety net for a forgotten clock-out. The cutoff is the
        most recent midnight on the **organization's** wall clock (its
        ``timezone``), so "midnight" falls where its people expect. Every
        open record that clocked in before that moment is closed at exactly
        that moment with ``closed_by = system``; records from today are left
        alone. Because the cutoff is "the last midnight", not "one day ago",
        a missed run just closes more records next time, and running it
        again immediately closes nothing, so it is safe to repeat.

        The employee never supplies the time: the cutoff is a guess, which is
        why the record says ``system`` and gives a reason. The employee and
        their manager are notified in-app (no email).

        Must run with the organization's RLS context already set. Never
        commits; the task that calls it does.

        Args:
            organization_id: Organization to close records for.
            now: The current moment; injectable so tests can fix the clock.

        Returns:
            How many records were closed.
        """
        now = now or datetime.now(UTC)
        organization = await self._org_repo.get_organization_by_id(organization_id)
        tz = ZoneInfo(organization.timezone)
        cutoff = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)

        closed = await self._repo.close_stale_open_records(cutoff, _AUTO_CLOSE_REASON)
        for record in closed:
            await self._audit.log_action(
                organization_id=organization_id,
                actor_user_id=None,
                action="auto_close",
                entity_type="attendance_record",
                entity_id=record.id,
                changes={
                    "old": {"clock_out_at": None},
                    "new": {
                        "clock_out_at": cutoff.isoformat(),
                        "closed_by": "system",
                        "close_reason": _AUTO_CLOSE_REASON,
                    },
                },
            )
            await self._notify_auto_close(organization_id, record, organization.timezone, tz)
        return len(closed)

    async def _notify_auto_close(
        self,
        organization_id: uuid.UUID,
        record: AttendanceRecord,
        timezone_name: str,
        tz: ZoneInfo,
    ) -> None:
        """Tell the employee, and their manager, that a record was closed for them.

        In-app only. Skips anyone without a login (an employee can exist
        without one) and never notifies the same person twice.

        Args:
            organization_id: Organization the record belongs to.
            record: The record the system just closed.
            timezone_name: The organization's timezone name, shown in the text.
            tz: The same timezone, for formatting the times.
        """
        employee = await self._employee_repo.get_employee_by_id(record.employee_id)
        if employee is None:
            return
        clocked_in = record.clock_in_at.astimezone(tz).strftime("%d %b %Y, %H:%M")
        closed_at = record.clock_out_at.astimezone(tz).strftime("%d %b %Y, %H:%M")
        name = f"{employee.first_name} {employee.last_name}"

        if employee.user_id is not None:
            await self._notifications.notify(
                organization_id=organization_id,
                recipient_user_ids=[employee.user_id],
                category=NotificationCategory.SYSTEM,
                title="You were clocked out automatically",
                body=(
                    f"You clocked in on {clocked_in} and didn't clock out. The record was closed "
                    f"automatically at midnight ({timezone_name}), {closed_at}. That clock-out "
                    "time is a system estimate, not something you recorded."
                ),
                link_type="attendance_record",
                link_id=record.id,
            )
        if employee.manager_id is not None:
            manager = await self._employee_repo.get_employee_by_id(employee.manager_id)
            if manager is not None and manager.user_id not in (None, employee.user_id):
                await self._notifications.notify(
                    organization_id=organization_id,
                    recipient_user_ids=[manager.user_id],
                    category=NotificationCategory.SYSTEM,
                    title=f"{name} didn't clock out",
                    body=(
                        f"{name} clocked in on {clocked_in} and didn't clock out. The record was "
                        f"closed automatically at midnight ({timezone_name}), {closed_at}."
                    ),
                    link_type="attendance_record",
                    link_id=record.id,
                )
