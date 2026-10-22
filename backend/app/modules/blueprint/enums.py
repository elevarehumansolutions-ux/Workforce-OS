"""Enum types for the blueprint module (the AI-proposed starting structure)."""

from enum import Enum


class BlueprintKind(str, Enum):
    """What one blueprint item proposes.

    Enforced as a database check constraint on ``blueprint_items``.
    """

    DEPARTMENT = "department"
    POSITION = "position"
    OBJECTIVE = "objective"
    KEY_RESULT = "key_result"
    # Clean-ups of what the company already has (the "sanitize" part).
    RENAME_DEPARTMENT = "rename_department"
    RENAME_POSITION = "rename_position"
    REVIEW_NOTE = "review_note"


class BlueprintStatus(str, Enum):
    """Review state of one item. Same words as AI suggestions use."""

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
