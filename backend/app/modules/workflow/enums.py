"""Enumerations used by the Workflow module's models and schemas."""

from enum import Enum


class InstanceStatus(str, Enum):
    """Where one running case (an instance of a template) is in its life.

    ``IN_PROGRESS`` is the starting state. ``COMPLETED`` (the last step's
    task is done or skipped) and ``CANCELLED`` (HR or the starter stopped it)
    are final: an instance never goes back to ``IN_PROGRESS``.
    See 08_DECISIONS.md 2026-10-12.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
