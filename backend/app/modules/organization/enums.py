"""Enumerations used by the organization module's models and schemas."""

from enum import Enum


class RiskLevel(str, Enum):
    """Risk level assigned to a position, from least to most critical."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class CriticalityType(str, Enum):
    """Category describing why a position matters to the business."""

    REVENUE_GENERATING = "revenue_generating"
    REVENUE_ENABLING = "revenue_enabling"
    OPERATIONAL = "operational"
    CUSTOMER = "customer"
    COMPLIANCE = "compliance"
    STRATEGIC = "strategic"
    FINANCIAL = "financial"
    LEGAL = "legal"
    REPUTATIONAL = "reputational"


class EmploymentType(str, Enum):
    """Employment arrangement under which an employee works."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERN = "intern"


class EmployeeStatus(str, Enum):
    """Lifecycle status of an employee record."""

    ACTIVE = "active"
    INACTIVE = "inactive"
