"""Pydantic request and response schemas for the Org Structure module."""

import decimal
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.schemas import NormalizedEmail
from app.modules.tenancy_identity.enums import MembershipRole

from .enums import CriticalityType, EmployeeStatus, EmploymentType, RiskLevel


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class LocationCreateRequest(BaseModel):
    """Request body for creating a location."""

    name: str
    address: str | None = None


class LocationUpdateRequest(BaseModel):
    """Request body for partially updating a location. All fields optional."""

    name: str | None = None
    address: str | None = None

    def has_updates(self) -> bool:
        """Return whether any field was explicitly set on this request."""
        return self.model_dump(exclude_unset=True) != {}


class LocationResponse(BaseModel):
    """API representation of a location, returned by location endpoints."""

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
    """Request body for creating a department."""

    name: str
    is_critical: bool = False
    revenue_allocation_percentage: decimal.Decimal | None = None


class DepartmentUpdateRequest(BaseModel):
    """Request body for partially updating a department. All fields optional.

    ``head_employee_id`` names the department's head (an active employee of
    the same organization). Send ``null`` to clear it; leave it out to keep
    it. It is not on the create request on purpose: during onboarding no
    employee exists yet, so the head is set afterwards (08_DECISIONS.md
    2026-10-06).
    """

    name: str | None = None
    is_critical: bool | None = None
    revenue_allocation_percentage: decimal.Decimal | None = None
    head_employee_id: uuid.UUID | None = None

    def has_updates(self) -> bool:
        """Return whether any field was explicitly set on this request."""
        return self.model_dump(exclude_unset=True) != {}


class DepartmentResponse(BaseModel):
    """API representation of a department, returned by department endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    is_critical: bool
    revenue_allocation_percentage: decimal.Decimal | None
    head_employee_id: uuid.UUID | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

class PositionCreateRequest(BaseModel):
    """Request body for creating a position."""

    department_id: uuid.UUID
    title: str
    is_critical: bool = False
    reports_to_position_id: uuid.UUID | None = None
    risk_level: RiskLevel | None = None
    criticality_type: CriticalityType | None = None


class PositionUpdateRequest(BaseModel):
    """Request body for partially updating a position. All fields optional."""

    department_id: uuid.UUID | None = None
    title: str | None = None
    is_critical: bool | None = None
    reports_to_position_id: uuid.UUID | None = None
    risk_level: RiskLevel | None = None
    criticality_type: CriticalityType | None = None

    def has_updates(self) -> bool:
        """Return whether any field was explicitly set on this request."""
        return self.model_dump(exclude_unset=True) != {}


class PositionResponse(BaseModel):
    """API representation of a position, returned by position endpoints."""

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
    """Request body for creating an employee.

    ``grant_login_access`` is the Add Employee screen's checkbox: when true,
    ``role`` is required and the employee is also given login access in the
    same call (an invite email, or a link to an existing account). It can't
    be combined with ``user_id``, which links an existing member directly.
    """

    position_id: uuid.UUID
    first_name: str
    last_name: str
    work_email: NormalizedEmail
    start_date: date
    user_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employee_code: str | None = None
    phone_number: str | None = None
    address: str | None = None
    employment_type: EmploymentType | None = None
    grant_login_access: bool = False
    role: MembershipRole | None = None

    @model_validator(mode="after")
    def _check_login_access_fields(self) -> "EmployeeCreateRequest":
        """Require a role with the checkbox, and refuse the checkbox with a user_id."""
        if self.grant_login_access and self.role is None:
            raise ValueError("role is required when grant_login_access is true")
        if self.grant_login_access and self.user_id is not None:
            raise ValueError("grant_login_access cannot be combined with user_id")
        return self


class EmployeeUpdateRequest(BaseModel):
    """Request body for partially updating an employee. All fields optional.

    Deliberately excludes `status` — offboarding/reinstating is a
    dedicated action (POST /employees/{id}/offboard|reinstate), not a
    generic field on this PATCH, per 08_DECISIONS.md 2026-09-20.
    """

    position_id: uuid.UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    work_email: NormalizedEmail | None = None
    start_date: date | None = None
    manager_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employee_code: str | None = None
    phone_number: str | None = None
    address: str | None = None
    employment_type: EmploymentType | None = None

    def has_updates(self) -> bool:
        """Return whether any field was explicitly set on this request."""
        return self.model_dump(exclude_unset=True) != {}


class EmployeeLinkUserRequest(BaseModel):
    """Request body for linking a login to an existing employee."""

    user_id: uuid.UUID


class EmployeeGrantLoginRequest(BaseModel):
    """Request body for giving an employee login access ("Send invite")."""

    role: MembershipRole


class EmployeeResponse(BaseModel):
    """API representation of an employee, returned by employee endpoints.

    ``invite_status`` is not a column: it says whether a login invite sent
    from this employee's row is still waiting. ``"pending"`` (the link still
    works), ``"expired"`` (it lapsed; send it again), or ``null`` (no invite
    waiting: the employee already has a login, or none was ever sent).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    invite_status: Literal["pending", "expired"] | None = None
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


class EmployeeGrantLoginResponse(BaseModel):
    """Result of giving an employee login access.

    ``outcome`` is ``"invited"`` (invite email sent), ``"added"`` (existing
    account added to the org and linked) or ``"linked"`` (existing org
    member linked, role unchanged).
    """

    outcome: str
    employee: EmployeeResponse
