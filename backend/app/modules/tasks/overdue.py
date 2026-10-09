"""The one definition of "overdue" for a task.

A task is overdue when it is not finished and its deadline has already passed.
Overdue is worked out when needed and never stored in the database.

The rule is written twice, side by side, so they stay the same:

- ``is_overdue`` checks ONE task in Python (for the "overdue" badge on a response).
- ``overdue_clause`` is the same rule as a database condition (for the
  ``?overdue=true`` filter, where the database checks many tasks at once).

Both take ``now`` as an argument instead of reading the clock themselves, so a
single request uses a single moment, and tests can pass any time they like.

Later (slice E) time a task was approved as "blocked" will not count as late.
Until then, this rule ignores blocks.
"""

from datetime import datetime

from sqlalchemy import and_

from .enums import OPEN_STATUSES
from .models import Task


def is_overdue(task: Task, now: datetime) -> bool:
    """Whether ``task`` is overdue at ``now``."""
    if task.due_at is None:
        return False  # no deadline, so it can never be late
    if task.status not in OPEN_STATUSES:
        return False  # finished or cancelled work is not overdue
    return task.due_at < now  # strictly before: exactly on the deadline is not late yet


def overdue_clause(now: datetime):
    """The database version of :func:`is_overdue`: deadline set, passed, and task still open."""
    return and_(
        Task.due_at.is_not(None),
        Task.due_at < now,
        Task.status.in_(OPEN_STATUSES),
    )
