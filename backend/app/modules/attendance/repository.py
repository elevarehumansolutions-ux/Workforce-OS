"""Data-access layer for the attendance module."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.core.schemas import PaginationResponse

from .enums import AttendanceClosedBy
from .models import AttendanceRecord

# The atomic close relies on RETURNING for the truth about what changed.
# synchronize_session=False stops SQLAlchemy guessing in Python which
# in-memory records the WHERE clause matched; populate_existing=True makes the
# returned row refresh any copy already loaded, so the caller sees real state.
# Same options as the AI module's atomic review UPDATEs.
_ATOMIC_UPDATE_OPTIONS = {"synchronize_session": False, "populate_existing": True}


class AttendanceRepository:
    """Handles persistence for attendance records within an organization."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with an RLS-scoped async session."""
        self._db = db

    async def get_open_record(self, employee_id: uuid.UUID) -> AttendanceRecord | None:
        """Get the employee's open record, i.e. the one they are clocked in on.

        "Currently clocked in" is derived, never stored: it means the
        employee has a record with ``clock_out_at IS NULL``. The partial
        unique index ``uq_attendance_one_open_per_employee`` guarantees there
        is at most one, so ``scalar_one_or_none`` can never see two. RLS
        already restricts this to the caller's current org.

        Args:
            employee_id: Id of the employee to look up.

        Returns:
            The open ``AttendanceRecord``, or ``None`` if the employee is not
            currently clocked in.
        """
        stmt = select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.clock_out_at.is_(None),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_records(
        self,
        employee_id: uuid.UUID,
        start: datetime | None = None,
        end: datetime | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List one employee's records, newest clock-in first.

        RLS already restricts this to the caller's current org.

        Args:
            employee_id: Employee whose history to list.
            start: Only records that clocked in at or after this moment.
            end: Only records that clocked in strictly before this moment.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``AttendanceRecord`` rows.
        """
        stmt = select(AttendanceRecord).where(AttendanceRecord.employee_id == employee_id)
        if start is not None:
            stmt = stmt.where(AttendanceRecord.clock_in_at >= start)
        if end is not None:
            stmt = stmt.where(AttendanceRecord.clock_in_at < end)
        stmt = stmt.order_by(AttendanceRecord.clock_in_at.desc())
        return await paginate(stmt, page, limit, self._db)

    async def create_open_record(
        self, organization_id: uuid.UUID, employee_id: uuid.UUID, clock_in_at: datetime
    ) -> AttendanceRecord | None:
        """Insert a new open record, or do nothing if the employee already has one.

        Uses ``INSERT ... ON CONFLICT DO NOTHING`` against the partial unique
        index ``uq_attendance_one_open_per_employee`` (``employee_id`` ``WHERE
        clock_out_at IS NULL``). The conflict target must match that index
        exactly, including its ``WHERE``, or Postgres rejects the statement.
        Two simultaneous clock-ins are therefore settled by the database in a
        single atomic statement: one inserts, the other gets ``None`` back.

        Args:
            organization_id: Organization the employee belongs to.
            employee_id: Employee who is clocking in.
            clock_in_at: The moment they clocked in.

        Returns:
            The newly created ``AttendanceRecord``, or ``None`` if the
            employee already had an open record.
        """
        stmt = (
            pg_insert(AttendanceRecord)
            .values(
                organization_id=organization_id,
                employee_id=employee_id,
                clock_in_at=clock_in_at,
            )
            .on_conflict_do_nothing(
                index_elements=[AttendanceRecord.employee_id],
                index_where=AttendanceRecord.clock_out_at.is_(None),
            )
            .returning(AttendanceRecord)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

    async def list_organizations_with_open_records(self) -> list[tuple[uuid.UUID, str]]:
        """List every organization that has anyone clocked in, across all tenants.

        The one deliberate exception to RLS in this module, and the Beat
        job's only way to discover which organizations to look at: with no
        tenant context set, RLS returns nothing. Calls the ``SECURITY
        DEFINER`` function ``organizations_with_open_attendance()`` (granted
        ``EXECUTE`` to the app role only, never ``BYPASSRLS``; see its
        migration for the full reasoning). It reveals just each such
        organization's id and timezone.

        Returns:
            ``(organization_id, timezone)`` for each organization with at
            least one open record.
        """
        result = await self._db.execute(
            text("SELECT organization_id, timezone FROM organizations_with_open_attendance()")
        )
        return [(row.organization_id, row.timezone) for row in result]

    async def close_stale_open_records(
        self, cutoff: datetime, close_reason: str
    ) -> list[AttendanceRecord]:
        """Atomically close every open record that clocked in before ``cutoff``, as the system.

        Must run with the organization's RLS context set, so it only ever
        touches that organization's records. The "still open?" check is part
        of the UPDATE (``WHERE clock_out_at IS NULL``), so it can't double-close
        a record an employee clocked out of a moment earlier, and running it
        twice closes nothing the second time. Records that clocked in at or
        after ``cutoff`` (today's, for a midnight cutoff) are left alone.

        Args:
            cutoff: The moment to close at; also the clock-in bound.
            close_reason: Why they were closed, stored on each record.

        Returns:
            The records this call closed (possibly none).
        """
        stmt = (
            update(AttendanceRecord)
            .where(
                AttendanceRecord.clock_out_at.is_(None),
                AttendanceRecord.clock_in_at < cutoff,
            )
            .values(
                clock_out_at=cutoff,
                closed_by=AttendanceClosedBy.SYSTEM.value,
                close_reason=close_reason,
            )
            .returning(AttendanceRecord)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return list(result.scalars().all())

    async def close_open_record(
        self,
        employee_id: uuid.UUID,
        clock_out_at: datetime,
        closed_by: AttendanceClosedBy,
        close_reason: str | None = None,
    ) -> AttendanceRecord | None:
        """Atomically close the employee's open record, if they have one.

        The "is it still open?" check is part of the UPDATE itself
        (``WHERE clock_out_at IS NULL``), so two simultaneous clock-outs can't
        both succeed: one closes the record, the other matches nothing and
        gets ``None``. Used for an employee clocking out and for the system's
        nightly auto-close alike; ``closed_by`` tells them apart.

        Sets ``clock_out_at``, ``closed_by`` and ``close_reason`` together,
        because ``check_attendance_closed_fields_together`` refuses a row
        where only some are set. Closing frees the employee's single
        open-record slot, so they can clock in again.

        ``clock_out_at`` is never earlier than the record's own ``clock_in_at``
        (``GREATEST``): a clock that runs slightly behind, or a cutoff that
        falls before a late clock-in, closes the record at zero length
        instead of violating ``check_attendance_out_after_in``.

        Args:
            employee_id: Employee whose open record should be closed.
            clock_out_at: When the record ended.
            closed_by: Who ended it, ``employee`` or ``system``.
            close_reason: Why the system closed it; ``None`` for an
                employee clock-out.

        Returns:
            The closed ``AttendanceRecord``, or ``None`` if the employee had
            no open record.
        """
        stmt = (
            update(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.clock_out_at.is_(None),
            )
            .values(
                clock_out_at=func.greatest(clock_out_at, AttendanceRecord.clock_in_at),
                closed_by=closed_by.value,
                close_reason=close_reason,
            )
            .returning(AttendanceRecord)
            .execution_options(**_ATOMIC_UPDATE_OPTIONS)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.scalar_one_or_none()

