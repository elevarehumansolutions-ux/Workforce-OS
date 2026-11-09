"""The money view of a case: is its figure on track, at risk, lost or secured?

A case can carry a figure (what the job is worth, for example a client's fee for
sourcing a role). Its tasks share it. This file holds the one rule that says what
state the figure is in, so the case page, the lists and the summary all agree.

It is a view next to the task marking (on time, late, never done), not part of it:
nothing here changes anyone's score.
"""

from datetime import datetime
from decimal import Decimal

NONE = "none"  # no figure entered for this case
ON_TRACK = "on_track"  # running, nothing late
AT_RISK = "at_risk"  # running, and a task of the case is overdue right now
LOST = "lost"  # cancelled, or the client's final deadline was missed
SECURED = "secured"  # finished by the client's final deadline (or no deadline was set)


def case_value_status(
    *,
    client_value: Decimal | None,
    deadline_at: datetime | None,
    status: str,
    completed_at: datetime | None,
    now: datetime,
    has_overdue_task: bool,
) -> str:
    """Work out the state of a case's figure.

    Args:
        client_value: The figure entered for the case, or None.
        deadline_at: The client's final deadline, or None.
        status: The case's status: in_progress, completed or cancelled.
        completed_at: When the case finished (only set when completed).
        now: The current time.
        has_overdue_task: Whether any open task of the case is overdue right now
            (the overdue rule of the Task module, which already ignores blocked tasks).
    """
    if client_value is None or client_value <= 0:
        return NONE
    if status == "cancelled":
        return LOST
    if status == "completed":
        # Finishing after the client's deadline still means the deadline was missed.
        if deadline_at is not None and completed_at is not None and completed_at > deadline_at:
            return LOST
        return SECURED
    # Still running.
    if deadline_at is not None and now > deadline_at:
        return LOST
    return AT_RISK if has_overdue_task else ON_TRACK


def value_amounts(client_value: Decimal | None, value_status: str) -> tuple[Decimal, Decimal]:
    """Return (value at risk, value lost) for a case: the figure sits in at most one of them."""
    if client_value is None:
        return Decimal(0), Decimal(0)
    if value_status == AT_RISK:
        return client_value, Decimal(0)
    if value_status == LOST:
        return Decimal(0), client_value
    return Decimal(0), Decimal(0)
