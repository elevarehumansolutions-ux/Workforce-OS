"""Enum types shared by the AI suggestions module's models and schemas."""

from enum import Enum


class SuggestionType(str, Enum):
    """The kind of thing an AI suggestion proposes.

    Enforced as a database check constraint on ``ai_suggestions``.
    ``kpi_weight`` is added in M8 once ``kpis`` exists — not a member yet.
    """

    CRITICAL_POSITION = "critical_position"
    REVENUE_ALLOCATION = "revenue_allocation"
    MISSING_DEPARTMENT = "missing_department"


class SuggestionStatus(str, Enum):
    """Review lifecycle state of an AI suggestion.

    Enforced as a database check constraint on ``ai_suggestions``.
    """

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class AIUsagePurpose(str, Enum):
    """What an LLM call recorded in ``ai_usage_log`` was made for.

    Enforced as a database check constraint on ``ai_usage_log``.
    """

    AI_SUGGESTION_GENERATION = "ai_suggestion_generation"
    EXECUTIVE_SUMMARY_GENERATION = "executive_summary_generation"


class ModelTier(str, Enum):
    """How much reasoning a job needs; config maps a tier to a concrete model."""

    FAST = "fast"
    STRONG = "strong"
