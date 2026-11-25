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


class CustomerRole(str, Enum):
    """The roles a customer company may give its own people.

    The same as ``MembershipRole`` without ``system_administrator``: that is Elevare's own platform
    role (08_DECISIONS.md 2026-09-02), never something a customer's HR may hand out. Request
    bodies use this class, so a request naming the platform role is refused with a 422.
    """

    HR_ADMINISTRATOR = "hr_administrator"
    MANAGER = "manager"
    BUSINESS_EXECUTIVE = "business_executive"
    EMPLOYEE = "employee"


class AccountStatus(str, Enum):
    """Lifecycle status of a user account, the single source of truth for account state."""

    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    BANNED = "banned"
