from enum import Enum


class RiskLevel(str, Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class CriticalityType(str, Enum):
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
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERN = "intern"


class EmployeeStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
