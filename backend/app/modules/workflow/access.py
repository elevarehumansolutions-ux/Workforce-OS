"""Who may see and build which workflow templates (08_DECISIONS.md 2026-11-14, "Templates belong to their department").

A template is seen, with its steps, only by the department that owns it (its members, and its head), plus HR
administrators and business executives. Starting a case from it needs the same access. HR may build for any
department; a ``manager`` builds only for their own department. Anyone else who is not allowed gets the same
"not found" as for a template that does not exist, so its existence is not revealed.

A person's department is the department of their position; the head of a department counts as belonging to it.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.repository import DepartmentRepository, EmployeeRepository, PositionRepository
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.models import Membership

# Roles that see every template in the organization.
_SEES_EVERY_TEMPLATE = (MembershipRole.HR_ADMINISTRATOR.value, MembershipRole.BUSINESS_EXECUTIVE.value)


class TemplateAccess:
    """What one caller may do with templates."""

    def __init__(self, role: str, department_ids: list[uuid.UUID]):
        """Store the caller's role and the departments they belong to."""
        self.role = role
        self.department_ids = department_ids
        self.sees_all = role in _SEES_EVERY_TEMPLATE

    def visible_department_ids(self) -> list[uuid.UUID] | None:
        """The departments whose templates the caller sees, or ``None`` for every department."""
        return None if self.sees_all else self.department_ids

    def can_see(self, template_department_id: uuid.UUID) -> bool:
        """Whether a template owned by this department is visible to the caller."""
        return self.sees_all or template_department_id in self.department_ids

    def can_build_for(self, template_department_id: uuid.UUID) -> bool:
        """Whether the caller may create or change a template owned by this department.

        The router has already limited building to HR administrators and managers; this adds that a manager
        may only build for their own department.
        """
        if self.role == MembershipRole.HR_ADMINISTRATOR.value:
            return True
        return template_department_id in self.department_ids


async def template_access_for(db: AsyncSession, caller: Membership) -> TemplateAccess:
    """Work out which departments the caller belongs to (their position's, and any they head)."""
    department_ids: list[uuid.UUID] = []
    employee = await EmployeeRepository(db).get_employee_by_user_id(caller.user_id)
    if employee is not None:
        position = await PositionRepository(db).get_position_by_id(employee.position_id)
        if position is not None:
            department_ids.append(position.department_id)
        for department in await DepartmentRepository(db).list_departments_headed_by(employee.id):
            if department.id not in department_ids:
                department_ids.append(department.id)
    return TemplateAccess(caller.role, department_ids)
