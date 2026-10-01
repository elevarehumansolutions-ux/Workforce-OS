"""Enumerations used by the KPI module's models and schemas."""

from enum import Enum


class KPITrackingMode(str, Enum):
    """How a KPI's mid-quarter progress is known.

    ``MANUAL`` (the default): a person types in the actual value via
    ``POST /kpis/{id}/scores``, updatable as often as needed while the
    quarter is still open. ``TASK_COUNT``: progress is a live count of
    completed tasks linked to this KPI within the current period — needs
    the ``tasks`` table (M10), not usable until then. See 08_DECISIONS.md
    2026-09-30.
    """

    MANUAL = "manual"
    TASK_COUNT = "task_count"
