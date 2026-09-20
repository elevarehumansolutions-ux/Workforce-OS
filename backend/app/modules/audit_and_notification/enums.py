from enum import Enum


class NotificationCategory(str, Enum):
    AI_SUGGESTION = "ai_suggestion"
    APPROVAL_REQUEST = "approval_request"
    TASK = "task"
    SYSTEM = "system"
