"""Enum types shared by the audit and notification module's models and schemas."""

from enum import Enum


class NotificationCategory(str, Enum):
    """The kind of event a notification was generated for.

    Used to filter a recipient's notification stream and enforced as a
    database check constraint on the ``notifications`` table.
    """

    AI_SUGGESTION = "ai_suggestion"
    APPROVAL_REQUEST = "approval_request"
    TASK = "task"
    SYSTEM = "system"
