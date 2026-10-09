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

from sqlalchemy import and_, func

from .enums import OPEN_STATUSES
from .models import Task


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
