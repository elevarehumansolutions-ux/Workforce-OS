from enum import Enum


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AuthProvider(str, Enum):
    PASSWORD = "password"
    MICROSOFT = "microsoft"
    GOOGLE = "google"


class MembershipRole(str, Enum):
    HR_ADMINISTRATOR = "hr_administrator"
    MANAGER = "manager"
    BUSINESS_EXECUTIVE = "business_executive"
    EMPLOYEE = "employee"
    SYSTEM_ADMINISTRATOR = "system_administrator"


class AccountStatus(str, Enum):
    """"""
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    BANNED = "banned"
