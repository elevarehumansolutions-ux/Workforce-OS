"""Enumerations used by the Task module's models and schemas."""

from enum import Enum


class TaskStatus(str, Enum):
    """Where a task is in its life.

    ``OPEN`` is the starting state. ``IN_PROGRESS`` means the assignee has
    started it. ``COMPLETED`` and ``CANCELLED`` are final: a completed task
    stays completed, and a cancelled one is never reopened (a new task is
    created instead). A cancelled task counts neither as completed nor as
    late. See 08_DECISIONS.md 2026-10-07.

    "Overdue" is deliberately **not** a value here. It is derived, not
    stored: a task that is ``OPEN`` or ``IN_PROGRESS`` with a ``due_at`` in
    the past (04_DATABASE.md, Cluster 6).
    """

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
