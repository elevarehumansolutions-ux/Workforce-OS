"""Enumerations used by the Scoring module's models and schemas."""

from enum import Enum


class SummarySource(str, Enum):
    """How an executive summary was written.

    ``AI`` means the language model wrote it and every number in it was
    checked against the facts. ``PLAIN`` is the fact-only fallback (for
    example "Operations: 90% (+12). Sales: 70% (-5).") saved when the model's
    wording still contained a wrong number after one retry.
    See 08_DECISIONS.md 2026-10-21, question 10.
    """

    AI = "ai"
    PLAIN = "plain"
