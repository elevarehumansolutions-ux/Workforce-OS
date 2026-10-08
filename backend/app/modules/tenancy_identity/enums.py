"""Enumerations used by the tenancy_identity module's models and schemas."""

from enum import Enum


class SubscriptionStatus(str, Enum):
    """Billing/subscription state of an organization."""

    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AuthProvider(str, Enum):
    """Mechanism a user authenticates with."""

    PASSWORD = "password"
    MICROSOFT = "microsoft"
    GOOGLE = "google"


class MembershipRole(str, Enum):
    """Role a user holds within a specific organization's membership."""

    HR_ADMINISTRATOR = "hr_administrator"
    MANAGER = "manager"
    BUSINESS_EXECUTIVE = "business_executive"
    EMPLOYEE = "employee"
    SYSTEM_ADMINISTRATOR = "system_administrator"


class AccountStatus(str, Enum):
    """Lifecycle status of a user account, the single source of truth for account state."""

    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    BANNED = "banned"
