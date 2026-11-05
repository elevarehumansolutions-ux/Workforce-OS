"""How a task is marked, and how marks become a score.

This file is plain logic: it never touches the database and never reads the
clock. The caller passes in the facts about a task and the moment to judge it
at, so every rule here can be tested with ordinary values.

The rules were settled with the user on 2026-10-21 (08_DECISIONS.md, M12
questions 1 to 3):

- A task is marked ON TIME (100 points), LATE (50) or NOT DONE (0).
- A task belongs to the period of its REAL deadline, which is its ``due_at``
  plus the blocked time a reviewer approved.
- A cancelled task, a task with no deadline and a task whose block is still
  waiting for review are left out.
- A task whose outcome only became known after its period closed (a block
  reviewed late) is marked in the period in which it was decided.
"""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

POINTS_ON_TIME = 100
POINTS_LATE = 50
POINTS_NOT_DONE = 0


class Mark(str, Enum):
    """How one task turned out, for scoring."""

    ON_TIME = "on_time"
    LATE = "late"
    NOT_DONE = "not_done"


class TaskFacts:
    """Everything the marking rule needs to know about one task.

    The caller fills this in from the task row and its blocks.

    Attributes:
        status: ``open``, ``in_progress``, ``completed`` or ``cancelled``.
        due_at: The written deadline, or None if the task has none.
        completed_at: When it was completed, or None.
        approved_blocked_seconds: Blocked time a reviewer approved (it moves
            the real deadline later).
        has_pending_block: True if any block of this task is still waiting
            for a reviewer's decision.
        last_block_reviewed_at: When the most recent block of this task was
            reviewed, or None if none has been.
    """

    def __init__(
        self,
        status: str,
        due_at: datetime | None,
        completed_at: datetime | None = None,
        approved_blocked_seconds: int = 0,
        has_pending_block: bool = False,
        last_block_reviewed_at: datetime | None = None,
    ):
        """Store the facts."""
        self.status = status
        self.due_at = due_at
        self.completed_at = completed_at
        self.approved_blocked_seconds = approved_blocked_seconds
        self.has_pending_block = has_pending_block
        self.last_block_reviewed_at = last_block_reviewed_at


def real_deadline(facts: TaskFacts) -> datetime:
    """The deadline a task is judged against: the written one plus approved blocked time.

    The same formula as ``tasks/overdue.py`` (a test keeps the two in step).
    Example: due on 1 September with a 3-day block approved gives 4 September.
    """
    return facts.due_at + timedelta(seconds=facts.approved_blocked_seconds)


def moment_it_counts(facts: TaskFacts) -> datetime:
    """The moment that decides which period a task is marked in.

    Normally this is the real deadline. But if a block was only reviewed AFTER
    that deadline, the outcome was not known on time, so the task counts from
    the moment it was reviewed. This is how a task whose review came after its
    period closed is carried into the next period instead of changing the
    closed one (08_DECISIONS.md 2026-10-21, question 3).
    Example: real deadline 30 September, reviewed on 10 October: it counts on
    10 October, in the next period.
    """
    deadline = real_deadline(facts)
    if facts.last_block_reviewed_at is not None and facts.last_block_reviewed_at > deadline:
        return facts.last_block_reviewed_at
    return deadline


def mark_task(
    facts: TaskFacts, period_start: datetime, period_end: datetime, now: datetime
) -> Mark | None:
    """Mark one task for one period, or return None if it does not count in it (yet).

    ``period_start`` is the first moment of the period and ``period_end`` the
    first moment AFTER it (so a deadline exactly at ``period_end`` belongs to the
    next period). ``now`` is the moment we are judging at: for a running period
    it is the current time; for the final write at period close the period's
    own end is used, so work finished after the period does not count in it.
    All datetimes must carry a timezone.

    Returns None when the task is left out:
    - it was cancelled (neither done nor late);
    - it has no deadline (lateness has nothing to be measured against);
    - one of its blocks is still waiting for review (held back until decided);
    - it does not belong to this period (see ``moment_it_counts``);
    - it is not finished and its deadline has not passed yet (not marked yet).
    """
    if facts.status == "cancelled":
        return None
    if facts.due_at is None:
        return None
    if facts.has_pending_block:
        return None
    if not (period_start <= moment_it_counts(facts) < period_end):
        return None

    judged_at = min(now, period_end)  # work finished after the period ends does not count in it
    deadline = real_deadline(facts)

    finished_in_time_to_count = (
        facts.status == "completed"
        and facts.completed_at is not None
        and facts.completed_at <= judged_at
    )
    if finished_in_time_to_count:
        if facts.completed_at <= deadline:
            return Mark.ON_TIME
        return Mark.LATE
    if deadline < judged_at:
        return Mark.NOT_DONE  # the deadline has passed and it was not finished
    return None  # not finished, but not due yet


def count_marks(marks: list[Mark | None]) -> tuple[int, int, int]:
    """Count a list of marks as (on time, late, not done). Tasks left out (None) are skipped."""
    on_time = 0
    late = 0
    not_done = 0
    for mark in marks:
        if mark == Mark.ON_TIME:
            on_time += 1
        elif mark == Mark.LATE:
            late += 1
        elif mark == Mark.NOT_DONE:
            not_done += 1
    return on_time, late, not_done


def score_from_counts(tasks_on_time: int, tasks_late: int, tasks_not_done: int) -> Decimal | None:
    """The score, 0 to 100, for these counts: the average of the tasks' points.

    Returns None when there are no tasks at all: "no data" is never 0.
    Example: 3 on time, 2 late and 1 not done is (3 x 100 + 2 x 50 + 0) / 6 = 66.67.
    """
    total = tasks_on_time + tasks_late + tasks_not_done
    if total == 0:
        return None
    points = (
        tasks_on_time * POINTS_ON_TIME
        + tasks_late * POINTS_LATE
        + tasks_not_done * POINTS_NOT_DONE
    )
    return (Decimal(points) / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
