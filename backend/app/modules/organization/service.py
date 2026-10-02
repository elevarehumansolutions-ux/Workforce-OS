"""Business logic for the organization structure module.

Each service wraps its matching repository, adding not-found checks,
delete-blocked-while-referenced guards, and audit logging around plain CRUD.
Services flush via the repository but never commit — the router commits
after a successful call.
"""

import uuid

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyExistsException,
    DepartmentNotFoundException,
    EmployeeAlreadyHasLoginException,
    EmployeeNotFoundException,
    EmployeeUserAlreadyLinkedException,
    LocationNotFoundException,
    MembershipDeactivatedException,
    PositionNotFoundException,
    ResourceInUseException,
    UserNotFoundException,
    ValidationException,
)
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.service import AuditService
from app.modules.tenancy_identity.models import Membership
from app.modules.tenancy_identity.service import MembershipService

from .enums import EmployeeStatus
from .models import Department, Employee, Location, Position
from .repository import DepartmentRepository, EmployeeRepository, LocationRepository, PositionRepository


def _snapshot(instance, fields) -> dict:
    """Capture a JSON-safe snapshot of an ORM instance's current values.

    Used for the audit log's 'old' side of a before/after diff.

    Args:
        instance: The ORM instance to read attribute values from.
        fields: Names of the attributes/columns to include.

    Returns:
        A JSON-encodable dict mapping each field name to its current value.
    """
    return jsonable_encoder({field: getattr(instance, field, None) for field in fields})


_DEPARTMENT_NAME_INDEX = "uq_departments_org_name_active"


def _is_duplicate_department_name(error: IntegrityError) -> bool:
    """Return whether an IntegrityError is the department-name uniqueness violation.

    Matches on the violated index's name rather than assuming any
    IntegrityError on ``departments`` means a duplicate name, so an
    unrelated constraint failure is never mislabelled as one.

    Args:
        error: The IntegrityError raised by the database driver.

    Returns:
        True if the per-organization unique department-name index was violated.
    """
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == _DEPARTMENT_NAME_INDEX


class LocationService:
    """Business logic for creating, reading, updating, and deleting locations."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = LocationRepository(db)
        self._audit = AuditService(db)

    async def create_location(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Location:
        """Create a location for an organization and record an audit entry.

        Args:
            organization_id: Organization the new location belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new location.

        Returns:
            The newly created ``Location``.
        """
        location = await self._repo.create_location({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="location",
            entity_id=location.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return location

    async def get_location_by_id(self, location_id: uuid.UUID) -> Location:
        """Fetch a location by id.

        Args:
            location_id: Id of the location to fetch.

        Returns:
            The matching ``Location``.

        Raises:
            LocationNotFoundException: If no non-deleted location with that
                id exists in the caller's org.
        """
        location = await self._repo.get_location_by_id(location_id)
        if location is None:
            raise LocationNotFoundException()
        return location

    async def list_locations(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted locations for an organization.

        Args:
            organization_id: Organization to list locations for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Location`` rows.
        """
        return await self._repo.list_locations(organization_id, page, limit)

    async def update_location(
        self, location_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Location:
        """Apply a partial update to a location and record an audit entry.

        Args:
            location_id: Id of the location to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Location``.

        Raises:
            LocationNotFoundException: If no non-deleted location with that
                id exists in the caller's org.
        """
        location = await self.get_location_by_id(location_id)
        old_data = _snapshot(location, data.keys())
        location = await self._repo.update_location(location, data)
        await self._audit.log_action(
            organization_id=location.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="location",
            entity_id=location.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return location

    async def delete_location(self, location_id: uuid.UUID, actor_user_id: uuid.UUID) -> Location:
        """Soft-delete a location and record an audit entry.

        Args:
            location_id: Id of the location to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``Location``.

        Raises:
            LocationNotFoundException: If no non-deleted location with that
                id exists in the caller's org.
        """
        location = await self.get_location_by_id(location_id)
        old_data = _snapshot(location, Location.__table__.columns.keys())
        location = await self._repo.soft_delete_location(location)
        await self._audit.log_action(
            organization_id=location.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="location",
            entity_id=location.id,
            changes={"old": old_data, "new": None},
        )
        return location


class DepartmentService:
    """Business logic for creating, reading, updating, and deleting departments."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = DepartmentRepository(db)
        self._audit = AuditService(db)

    async def create_department(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Department:
        """Create a department for an organization and record an audit entry.

        Args:
            organization_id: Organization the new department belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new department.

        Returns:
            The newly created ``Department``.

        Raises:
            AlreadyExistsException: If a non-deleted department with the same
                (normalized) name already exists in the organization.
        """
        try:
            # A SAVEPOINT, so a rejected insert doesn't abort the surrounding
            # transaction (and with it the tenant context set for this request).
            async with self._db.begin_nested():
                department = await self._repo.create_department(
                    {**data, "organization_id": organization_id}
                )
        except IntegrityError as error:
            if _is_duplicate_department_name(error):
                raise AlreadyExistsException(
                    message=f"A department named '{data['name']}' already exists"
                ) from error
            raise
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="department",
            entity_id=department.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return department

    async def get_department_by_id(self, department_id: uuid.UUID) -> Department:
        """Fetch a department by id.

        Args:
            department_id: Id of the department to fetch.

        Returns:
            The matching ``Department``.

        Raises:
            DepartmentNotFoundException: If no non-deleted department with
                that id exists in the caller's org.
        """
        department = await self._repo.get_department_by_id(department_id)
        if department is None:
            raise DepartmentNotFoundException()
        return department

    async def list_departments(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted departments for an organization.

        Args:
            organization_id: Organization to list departments for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Department`` rows.
        """
        return await self._repo.list_departments(organization_id, page, limit)

    async def update_department(
        self, department_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Department:
        """Apply a partial update to a department and record an audit entry.

        Args:
            department_id: Id of the department to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Department``.

        Raises:
            DepartmentNotFoundException: If no non-deleted department with
                that id exists in the caller's org.
            AlreadyExistsException: If renaming would duplicate another
                non-deleted department's (normalized) name in the org.
        """
        department = await self.get_department_by_id(department_id)
        old_data = _snapshot(department, data.keys())
        try:
            async with self._db.begin_nested():
                department = await self._repo.update_department(department, data)
        except IntegrityError as error:
            if _is_duplicate_department_name(error):
                raise AlreadyExistsException(
                    message=f"A department named '{data['name']}' already exists"
                ) from error
            raise
        await self._audit.log_action(
            organization_id=department.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="department",
            entity_id=department.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return department

    async def delete_department(self, department_id: uuid.UUID, actor_user_id: uuid.UUID) -> Department:
        """Soft-delete a department, blocking while it is still referenced.

        Deletion is blocked-while-referenced rather than cascaded
        (01_REQUIREMENTS.md §2, 08_DECISIONS.md 2026-09-07).

        Args:
            department_id: Id of the department to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``Department``.

        Raises:
            DepartmentNotFoundException: If no non-deleted department with
                that id exists in the caller's org.
            ResourceInUseException: If the department still has active
                positions assigned to it, or a pending AI suggestion targets it.
        """
        # Blocked-while-referenced, not cascaded (01_REQUIREMENTS.md §2,
        # 08_DECISIONS.md 2026-09-07) — named reason, no silent allow.
        department = await self.get_department_by_id(department_id)

        active_positions = await self._repo.count_active_positions(department_id)
        has_pending_suggestion = await self._repo.has_pending_ai_suggestion(department_id)
        reasons = []
        if active_positions > 0:
            reasons.append(f"{active_positions} active position(s) still assigned")
        if has_pending_suggestion:
            reasons.append("a pending AI suggestion still targets it (review it first)")
        if reasons:
            raise ResourceInUseException(message=f"Cannot delete department: {'; '.join(reasons)}")

        old_data = _snapshot(department, Department.__table__.columns.keys())
        department = await self._repo.soft_delete_department(department)
        await self._audit.log_action(
            organization_id=department.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="department",
            entity_id=department.id,
            changes={"old": old_data, "new": None},
        )
        return department


class PositionService:
    """Business logic for creating, reading, updating, and deleting positions."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = PositionRepository(db)
        self._audit = AuditService(db)

    async def create_position(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Position:
        """Create a position for an organization and record an audit entry.

        Args:
            organization_id: Organization the new position belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new position.

        Returns:
            The newly created ``Position``.
        """
        position = await self._repo.create_position({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="position",
            entity_id=position.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return position

    async def get_position_by_id(self, position_id: uuid.UUID) -> Position:
        """Fetch a position by id.

        Args:
            position_id: Id of the position to fetch.

        Returns:
            The matching ``Position``.

        Raises:
            PositionNotFoundException: If no non-deleted position with that
                id exists in the caller's org.
        """
        position = await self._repo.get_position_by_id(position_id)
        if position is None:
            raise PositionNotFoundException()
        return position

    async def list_positions(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted positions for an organization.

        Args:
            organization_id: Organization to list positions for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Position`` rows.
        """
        return await self._repo.list_positions(organization_id, page, limit)

    async def update_position(
        self, position_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Position:
        """Apply a partial update to a position and record an audit entry.

        Args:
            position_id: Id of the position to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Position``.

        Raises:
            PositionNotFoundException: If no non-deleted position with that
                id exists in the caller's org.
        """
        position = await self.get_position_by_id(position_id)
        old_data = _snapshot(position, data.keys())
        position = await self._repo.update_position(position, data)
        await self._audit.log_action(
            organization_id=position.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="position",
            entity_id=position.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return position

    async def delete_position(self, position_id: uuid.UUID, actor_user_id: uuid.UUID) -> Position:
        """Soft-delete a position, blocking while it is still referenced.

        Blocked-while-referenced against three independent references: active
        employees holding this position, other positions reporting to it, and
        a pending AI suggestion targeting it. All are checked and reported
        together in a single error.

        Args:
            position_id: Id of the position to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``Position``.

        Raises:
            PositionNotFoundException: If no non-deleted position with that
                id exists in the caller's org.
            ResourceInUseException: If the position still has active
                employees assigned to it, positions reporting to it, or a
                pending AI suggestion targeting it.
        """
        # Same blocked-while-referenced rule as DepartmentService.delete_department,
        # checked against two independent references (active employees holding
        # this position, other positions reporting to it) and reported together.
        position = await self.get_position_by_id(position_id)

        active_employees = await self._repo.count_active_employees(position_id)
        direct_reports = await self._repo.count_direct_reports(position_id)
        has_pending_suggestion = await self._repo.has_pending_ai_suggestion(position_id)
        reasons = []
        if active_employees > 0:
            reasons.append(f"{active_employees} active employee(s) still assigned")
        if direct_reports > 0:
            reasons.append(f"{direct_reports} position(s) still reporting to it")
        if has_pending_suggestion:
            reasons.append("a pending AI suggestion still targets it (review it first)")
        if reasons:
            raise ResourceInUseException(message=f"Cannot delete position: {'; '.join(reasons)}")

        old_data = _snapshot(position, Position.__table__.columns.keys())
        position = await self._repo.soft_delete_position(position)
        await self._audit.log_action(
            organization_id=position.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="position",
            entity_id=position.id,
            changes={"old": old_data, "new": None},
        )
        return position


class EmployeeService:
    """Business logic for creating, reading, updating, offboarding, and reinstating employees."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = EmployeeRepository(db)
        self._audit = AuditService(db)
        self._membership_service = MembershipService(db)
    
    async def _validate_user_link(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Check a user can be linked to an employee in this organization.

        Args:
            organization_id: Organization the employee belongs to.
            user_id: User being linked.

        Raises:
            UserNotFoundException: If the user has no membership in this
                organization.
            MembershipDeactivatedException: If the user's membership in
                this organization is deactivated.
            EmployeeUserAlreadyLinkedException: If another non-deleted
                employee in this organization is already linked to the user.
        """
        membership = await self._membership_service.get_membership(user_id, organization_id)
        if membership is None:
            raise UserNotFoundException()
        if membership.deactivated_at is not None:
            raise MembershipDeactivatedException()

        if await self._repo.get_employee_by_user_id(user_id) is not None:
            raise EmployeeUserAlreadyLinkedException()

    async def create_employee(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Employee:
        """Create an employee for an organization and record an audit entry.

        Args:
            organization_id: Organization the new employee belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new employee.

        Returns:
            The newly created ``Employee``.
        """
        if data.get("user_id") is not None:
            await self._validate_user_link(organization_id, data["user_id"])
        employee = await self._repo.create_employee({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="employee",
            entity_id=employee.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return employee

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee:
        """Fetch an employee by id.

        Args:
            employee_id: Id of the employee to fetch.

        Returns:
            The matching ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
        """
        employee = await self._repo.get_employee_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundException()
        return employee

    async def list_employees(
        self,
        organization_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted employees for an organization.

        Args:
            organization_id: Organization to list employees for.
            location_id: If given, restrict results to this location.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Employee`` rows.
        """
        return await self._repo.list_employees(organization_id, location_id, page, limit)

    async def list_members_without_employee(
        self, organization_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List active org members who have no employee record.

        Args:
            organization_id: Organization to list members for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``Membership`` rows.
        """
        return await self._repo.list_members_without_employee(organization_id, page, limit)

    async def update_employee(
        self, employee_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> Employee:
        """Apply a partial update to an employee and record an audit entry.

        Args:
            employee_id: Id of the employee to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
        """
        employee = await self.get_employee_by_id(employee_id)
        old_data = _snapshot(employee, data.keys())
        employee = await self._repo.update_employee(employee, data)
        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="employee",
            entity_id=employee.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return employee

    async def link_user(
        self, employee_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> Employee:
        """Link a login to an existing employee that does not have one.

        One-way by design: ``user_id`` is never cleared or swapped once set,
        because offboarding finds the login to deactivate through it.

        Args:
            employee_id: Id of the employee to link.
            user_id: User to link as this employee's login.
            actor_user_id: User performing the link, for the audit log.

        Returns:
            The updated ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
            EmployeeAlreadyHasLoginException: If the employee already has a
                login linked.
        """
        employee = await self.get_employee_by_id(employee_id)
        if employee.user_id is not None:
            raise EmployeeAlreadyHasLoginException()
        return await self._attach_user(employee, user_id, actor_user_id)

    async def _attach_user(
        self, employee: Employee, user_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> Employee:
        """Validate a user, set it as the employee's login, and audit-log it.

        Args:
            employee: Employee with no login yet.
            user_id: User to attach.
            actor_user_id: User performing the link, for the audit log.

        Returns:
            The updated ``Employee``.

        Raises:
            UserNotFoundException: If the user is not a member of the org.
            MembershipDeactivatedException: If the user's membership is
                deactivated.
            EmployeeUserAlreadyLinkedException: If another employee already
                holds the user.
        """
        await self._validate_user_link(employee.organization_id, user_id)
        employee = await self._repo.update_employee(employee, {"user_id": user_id})
        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=actor_user_id,
            action="link_user",
            entity_type="employee",
            entity_id=employee.id,
            changes={"old": {"user_id": None}, "new": {"user_id": str(user_id)}},
        )
        return employee

    async def grant_login(
        self, employee_id: uuid.UUID, role: str, actor_user_id: uuid.UUID
    ) -> tuple[str, Employee, str | None]:
        """Give an employee login access: link their account or send an invite.

        Uses the employee's ``work_email``. The outcome depends on that email:

        - an active member of this org already has it: the employee is linked
          to them now, their role is left unchanged (``"linked"``);
        - a user has it but no membership here: they are added with ``role``
          and linked now (``"added"``); a deactivated member is refused
          instead, since bringing them back is the reactivate action;
        - nobody has it: an invite carrying this employee is created
          (``"invited"``); accepting it links the new user. Calling this
          again replaces the pending invite, which is how a resend works.

        Args:
            employee_id: Employee to give login access.
            role: Role to grant when a membership or invite is created.
            actor_user_id: User performing the action, for the audit log.

        Returns:
            ``(outcome, employee, raw_invite_token)``; the token is set only
            for ``"invited"``, so the caller can send the email after commit.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
            EmployeeAlreadyHasLoginException: If the employee already has a
                login linked.
            MembershipDeactivatedException: If the email belongs to a
                member who is deactivated in this organization.
            ValidationException: If the employee is offboarded.
        """
        employee = await self.get_employee_by_id(employee_id)
        if employee.user_id is not None:
            raise EmployeeAlreadyHasLoginException()
        if employee.status == EmployeeStatus.INACTIVE.value:
            raise ValidationException(message="Reinstate this employee before granting login access")

        email = employee.work_email.strip()
        existing = await self._membership_service.get_membership_by_email(email, employee.organization_id)
        if existing is not None and existing.deactivated_at is None:
            employee = await self._attach_user(employee, existing.user_id, actor_user_id)
            return "linked", employee, None

        outcome, result = await self._membership_service.invite_teammate(
            organization_id=employee.organization_id,
            invited_by_user_id=actor_user_id,
            email=email,
            role=role,
            employee_id=employee.id,
        )
        if outcome == "added":
            employee = await self._attach_user(employee, result.user_id, actor_user_id)
            return "added", employee, None
        return "invited", employee, result.raw_token

    async def link_accepted_invite(self, employee_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Link a newly created user to the employee their invite was for.

        Called while accepting an invite, so it must never raise: a person
        who accepted a valid invite is not locked out because the employee
        record changed in the meantime. If the employee is gone, offboarded,
        or already has a login, nothing is linked and HR links manually.

        Args:
            employee_id: Employee stored on the accepted invite.
            user_id: The user just created from the invite.

        Returns:
            ``True`` if the user was linked, ``False`` if it was skipped.
        """
        employee = await self._repo.get_employee_by_id(employee_id)
        if (
            employee is None
            or employee.user_id is not None
            or employee.status == EmployeeStatus.INACTIVE.value
        ):
            return False
        await self._repo.update_employee(employee, {"user_id": user_id})
        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=user_id,
            action="link_user",
            entity_type="employee",
            entity_id=employee.id,
            changes={"old": {"user_id": None}, "new": {"user_id": str(user_id)}},
        )
        return True

    async def offboard_employee(self, employee_id: uuid.UUID, caller: Membership) -> Employee:
        """Offboard an employee: set them inactive and deactivate their login.

        Dedicated offboarding action (08_DECISIONS.md 2026-09-20), not a
        generic status PATCH. If the employee has login access, deactivates
        their linked ``Membership`` in the same transaction, going through
        ``MembershipService.update_membership`` so its guardrails apply (an
        HR Administrator can't offboard themselves or the org's Owner this
        way). Does not block on the employee having direct reports (same
        decision) — that count is informational only, logged for context.

        Args:
            employee_id: Id of the employee to offboard.
            caller: The acting membership; passed through so
                ``MembershipService`` guardrails apply when deactivating a
                linked membership.

        Returns:
            The updated, now-inactive ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
            ValidationException: If the employee is already offboarded.
        """
        employee = await self.get_employee_by_id(employee_id)
        if employee.status == EmployeeStatus.INACTIVE.value:
            raise ValidationException(message="Employee is already offboarded")

        old_status = employee.status
        employee = await self._repo.update_employee(employee, {"status": EmployeeStatus.INACTIVE.value})

        membership_deactivated = False
        if employee.user_id is not None:
            membership = await self._membership_service.get_membership(
                employee.user_id, employee.organization_id
            )
            if membership is not None and membership.deactivated_at is None:
                await self._membership_service.update_membership(
                    target=membership, caller=caller, role=None, is_deactivated=True
                )
                membership_deactivated = True

        direct_reports = await self._repo.count_direct_reports(employee_id)
        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=caller.user_id,
            action="offboard",
            entity_type="employee",
            entity_id=employee.id,
            changes={
                "old": {"status": old_status},
                "new": {"status": employee.status},
                "membership_deactivated": membership_deactivated,
                "direct_reports_at_time": direct_reports,
            },
        )
        return employee

    async def reinstate_employee(self, employee_id: uuid.UUID, caller: Membership) -> Employee:
        """Reinstate a previously offboarded employee.

        Mirror of ``offboard_employee`` — reverses a termination (wrongful
        termination, rehire). Restores active status and re-enables login
        access if it was deactivated by an earlier offboard.

        Args:
            employee_id: Id of the employee to reinstate.
            caller: The acting membership; passed through so
                ``MembershipService`` guardrails apply when reactivating a
                linked membership.

        Returns:
            The updated, now-active ``Employee``.

        Raises:
            EmployeeNotFoundException: If no non-deleted employee with that
                id exists in the caller's org.
            ValidationException: If the employee is already active.
        """
        employee = await self.get_employee_by_id(employee_id)
        if employee.status == EmployeeStatus.ACTIVE.value:
            raise ValidationException(message="Employee is already active")

        old_status = employee.status
        employee = await self._repo.update_employee(employee, {"status": EmployeeStatus.ACTIVE.value})

        membership_reactivated = False
        if employee.user_id is not None:
            membership = await self._membership_service.get_membership(
                employee.user_id, employee.organization_id
            )
            if membership is not None and membership.deactivated_at is not None:
                await self._membership_service.update_membership(
                    target=membership, caller=caller, role=None, is_deactivated=False
                )
                membership_reactivated = True

        await self._audit.log_action(
            organization_id=employee.organization_id,
            actor_user_id=caller.user_id,
            action="reinstate",
            entity_type="employee",
            entity_id=employee.id,
            changes={
                "old": {"status": old_status},
                "new": {"status": employee.status},
                "membership_reactivated": membership_reactivated,
            },
        )
        return employee
