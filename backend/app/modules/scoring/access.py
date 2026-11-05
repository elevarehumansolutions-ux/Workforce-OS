"""Who may see whose performance numbers (08_DECISIONS.md 2026-10-21, question 8).

One object answers the question for every performance read, so the rule is
written once and cannot drift between endpoints. It follows the same shape as
``TaskScope`` in the Task module.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.repository import (
    DepartmentRepository,
    EmployeeRepository,
    PositionRepository,
)
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.models import Membership

# Roles that can see every score in the organization.
_ORG_WIDE_ROLES = [MembershipRole.HR_ADMINISTRATOR.value, MembershipRole.BUSINESS_EXECUTIVE.value]


class PerformanceScope:
    """Which people and departments a caller may see scores for.

    HR administrators and business executives see everyone. A department head
    sees the departments they head; a ``manager`` also sees the department they
    belong to. Everyone else sees only their own score.

    Attributes:
        sees_all: True for roles with an organization-wide view.
        employee_id: The caller's own employee id, or ``None`` if they have no
            employee record (a founder or HR administrator often has none).
        department_ids: Departments whose people the caller may see.
    """

    def __init__(
        self,
        sees_all: bool,
        employee_id: uuid.UUID | None,
        department_ids: list[uuid.UUID],
    ):
        """Store who the caller is and what they are allowed to see."""
        self.sees_all = sees_all
        self.employee_id = employee_id
        self.department_ids = department_ids

    def can_see_department(self, department_id: uuid.UUID) -> bool:
        """Whether the caller may see this department's scores."""
        if self.sees_all:
            return True
        return department_id in self.department_ids

    def can_see_person(self, employee_id: uuid.UUID, department_id: uuid.UUID | None) -> bool:
        """Whether the caller may see this person's score.

        Args:
            employee_id: The person whose score is being asked for.
            department_id: The department that person works in, or ``None``
                if their position has no department.
        """
        if self.sees_all:
            return True
        if self.employee_id is not None and employee_id == self.employee_id:
            return True
        if department_id is not None and department_id in self.department_ids:
            return True
        return False

    def can_see_company(self) -> bool:
        """Whether the caller may see the company-wide view (HR and executives only)."""
        return self.sees_all

    def can_see_ranked_list(self) -> bool:
        """Whether the caller may see a named list of people ranked by score.

        An ordinary employee does not get a list of colleagues' scores. A head
        or manager already sees the people of their department one by one, so
        a ranked list of those same people shows them nothing new.
        """
        return self.sees_all or len(self.department_ids) > 0


async def load_performance_scope(db: AsyncSession, caller: Membership) -> PerformanceScope:
    """Work out what ``caller`` may see, from their role, position and headed departments.

    Args:
        db: Database session (already tied to the caller's organization).
        caller: The caller's membership.
    """
    employee_repo = EmployeeRepository(db)
    position_repo = PositionRepository(db)
    department_repo = DepartmentRepository(db)

    employee = await employee_repo.get_employee_by_user_id(caller.user_id)

    employee_id = None
    department_ids = []

    # A caller with no employee record heads nothing and belongs to no department.
    if employee is not None:
        employee_id = employee.id

        headed_departments = await department_repo.list_departments_headed_by(employee.id)
        for department in headed_departments:
            department_ids.append(department.id)

        # Only the manager role also sees the department they belong to.
        if caller.role == MembershipRole.MANAGER.value:
            position = await position_repo.get_position_by_id(employee.position_id)
            if position is not None and position.department_id not in department_ids:
                department_ids.append(position.department_id)

    return PerformanceScope(
        sees_all=caller.role in _ORG_WIDE_ROLES,
        employee_id=employee_id,
        department_ids=department_ids,
    )
