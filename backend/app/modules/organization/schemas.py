"""Pydantic request and response schemas for the Org Structure module."""

import decimal
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .enums import CriticalityType, EmployeeStatus, EmploymentType, RiskLevel


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class LocationCreateRequest(BaseModel):
    name: str
    address: str | None = None


class LocationUpdateRequest(BaseModel):
    name: str | None = None
    address: str | None = None

    def has_updates(self) -> bool:
        return self.model_dump(exclude_unset=True) != {}


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    address: str | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class DepartmentCreateRequest(BaseModel):
    name: str
    is_critical: bool = False
    revenue_allocation_percentage: decimal.Decimal | None = None


class DepartmentUpdateRequest(BaseModel):
    name: str | None = None
    is_critical: bool | None = None
    revenue_allocation_percentage: decimal.Decimal | None = None

    def has_updates(self) -> bool:
        return self.model_dump(exclude_unset=True) != {}


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    is_critical: bool
    revenue_allocation_percentage: decimal.Decimal | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

class PositionCreateRequest(BaseModel):
    department_id: uuid.UUID
    title: str
    is_critical: bool = False
    reports_to_position_id: uuid.UUID | None = None
    risk_level: RiskLevel | None = None
    criticality_type: CriticalityType | None = None


class PositionUpdateRequest(BaseModel):
    department_id: uuid.UUID | None = None
    title: str | None = None
    is_critical: bool | None = None
    reports_to_position_id: uuid.UUID | None = None
    risk_level: RiskLevel | None = None
    criticality_type: CriticalityType | None = None

    def has_updates(self) -> bool:
        return self.model_dump(exclude_unset=True) != {}


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID
    title: str
    is_critical: bool
    reports_to_position_id: uuid.UUID | None
    risk_level: RiskLevel | None
    criticality_type: CriticalityType | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

class EmployeeCreateRequest(BaseModel):
    position_id: uuid.UUID
    first_name: str
    last_name: str
    work_email: str
    start_date: date
    user_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employee_code: str | None = None
    phone_number: str | None = None
    address: str | None = None
    employment_type: EmploymentType | None = None


class EmployeeUpdateRequest(BaseModel):
    """Deliberately excludes `status` — offboarding/reinstating is a
    dedicated action (POST /employees/{id}/offboard|reinstate), not a
    generic field on this PATCH, per 08_DECISIONS.md 2026-09-20."""

    position_id: uuid.UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    work_email: str | None = None
    start_date: date | None = None
    manager_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employee_code: str | None = None
    phone_number: str | None = None
    address: str | None = None
    employment_type: EmploymentType | None = None

    def has_updates(self) -> bool:
        return self.model_dump(exclude_unset=True) != {}


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    position_id: uuid.UUID
    manager_id: uuid.UUID | None
    location_id: uuid.UUID | None
    employee_code: str | None
    first_name: str
    last_name: str
    work_email: str
    phone_number: str | None
    address: str | None
    employment_type: EmploymentType | None
    start_date: date
    status: EmployeeStatus
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
