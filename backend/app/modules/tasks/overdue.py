"""The one definition of "overdue" for a task.

A task is overdue when it is not finished and its deadline has already passed.
Overdue is worked out when needed and never stored in the database.

The rule is written twice, side by side, so they stay the same:

- ``is_overdue`` checks ONE task in Python (for the "overdue" badge on a response).
- ``overdue_clause`` is the same rule as a database condition (for the
  ``?overdue=true`` filter, where the database checks many tasks at once).

Both take ``now`` as an argument instead of reading the clock themselves, so a
single request uses a single moment, and tests can pass any time they like.

Blocked time (08_DECISIONS.md 2026-10-09): a task that is blocked right now is
never overdue, and blocked time a reviewer approved pushes the real deadline
later. ``due_at`` itself never changes. The real deadline is
``due_at`` plus the task's ``approved_blocked_seconds``.
"""

from datetime import datetime, timedelta

from sqlalchemy import and_, func, text

from .enums import OPEN_STATUSES
from .models import Task

# The reminder before a deadline (08_DECISIONS.md 2026-11-15): sent once, to the assignee, when a quarter of the
# task's time is left, but never less than 1 hour before the deadline and never more than 1 day before it. A task
# whose whole life is no longer than that window gets no reminder. (The overdue alert covers it after the deadline.)
REMINDER_SHARE_OF_TIME = 0.25
REMINDER_MIN_LEAD = timedelta(hours=1)
REMINDER_MAX_LEAD = timedelta(days=1)


def reminder_lead(task_life: timedelta) -> timedelta:
    """How long before the real deadline the reminder is due, for a task that lives ``task_life`` in all."""
    return min(max(task_life * REMINDER_SHARE_OF_TIME, REMINDER_MIN_LEAD), REMINDER_MAX_LEAD)


def is_due_soon(task: Task, now: datetime) -> bool:
    """Whether ``task`` is inside its reminder window at ``now`` and has not been reminded yet.

    The Python twin of :func:`due_soon_clause` (and of the lookup function in migration a1d7c3f95e48).
    """
    if task.due_at is None or task.assigned_to_employee_id is None:
        return False  # nobody to remind
    if task.status not in OPEN_STATUSES or task.blocked_since is not None:
        return False
    if task.due_soon_notified_at is not None:
        return False  # already reminded for this deadline
    real_deadline = task.due_at + timedelta(seconds=task.approved_blocked_seconds)
    if real_deadline <= now:
        return False  # past the deadline: the overdue alert's job
    task_life = real_deadline - task.created_at
    lead = reminder_lead(task_life)
    return (real_deadline - now) <= lead and task_life > lead


def is_overdue(task: Task, now: datetime) -> bool:
    """Whether ``task`` is overdue at ``now``."""
    if task.due_at is None:
        return False  # no deadline, so it can never be late
    if task.status not in OPEN_STATUSES:
        return False  # finished or cancelled work is not overdue
    if task.blocked_since is not None:
        return False  # blocked right now: waiting on something outside the assignee's hands
    real_deadline = task.due_at + timedelta(seconds=task.approved_blocked_seconds)
    return real_deadline < now  # strictly before: exactly on the deadline is not late yet


def due_soon_clause(now: datetime):
    """The database version of :func:`is_due_soon`, as one SQL condition on the ``tasks`` table.

    Written as text because it works in intervals; keep it the same as the Python function and the lookup.
    """
    real = "(tasks.due_at + make_interval(secs => tasks.approved_blocked_seconds))"
    lead = f"LEAST(GREATEST(({real} - tasks.created_at) * 0.25, interval '1 hour'), interval '1 day')"
    statuses = ", ".join(f"'{status}'" for status in OPEN_STATUSES)
    return text(
        f"tasks.due_at IS NOT NULL AND tasks.assigned_to_employee_id IS NOT NULL"
        f" AND tasks.blocked_since IS NULL AND tasks.due_soon_notified_at IS NULL"
        f" AND tasks.status IN ({statuses})"
        f" AND {real} > CAST(:now AS timestamptz)"
        f" AND {real} - CAST(:now AS timestamptz) <= {lead}"
        f" AND {real} - tasks.created_at > {lead}"
    ).bindparams(now=now)


def overdue_clause(now: datetime):
    """The database version of :func:`is_overdue`: the same checks, written for a query."""
    # make_interval(years, months, weeks, days, hours, mins, secs) builds a length of
    # time from a number of seconds, which Postgres needs before it can add it to a date.
    approved_blocked_time = func.make_interval(0, 0, 0, 0, 0, 0, Task.approved_blocked_seconds)
    return and_(
        Task.due_at.is_not(None),
        Task.status.in_(OPEN_STATUSES),
        Task.blocked_since.is_(None),
        Task.due_at + approved_blocked_time < now,
    )
