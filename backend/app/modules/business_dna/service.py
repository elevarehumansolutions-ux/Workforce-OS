"""Business logic for the Business DNA module.

Wraps BusinessDNARepository/BusinessDNACoreValueRepository, adding
not-found checks, the upsert logic, and audit logging around plain CRUD.
Services flush via the repository but never commit — the router commits
after a successful call, same convention as the organization module.
"""

import uuid

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessDNACoreValueNotFoundException,
    BusinessDNANotFoundException,
)
from app.modules.audit_and_notification.service import AuditService
from app.modules.tenancy_identity.repository import OrganizationRepository

from .models import BusinessDNA, BusinessDNACoreValue
from .repository import BusinessDNACoreValueRepository, BusinessDNARepository


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


class BusinessDNAService:
    """Business logic for reading and upserting an org's Business DNA profile."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = BusinessDNARepository(db)
        self._org_repo = OrganizationRepository(db)
        self._audit = AuditService(db)

    async def get_business_dna(self, organization_id: uuid.UUID) -> BusinessDNA:
        """Fetch the org's Business DNA profile.

        Args:
            organization_id: Organization to fetch the profile for.

        Returns:
            The matching ``BusinessDNA``.

        Raises:
            BusinessDNANotFoundException: If the org hasn't filled it in yet.
        """
        business_dna = await self._repo.get_business_dna_by_organization_id(organization_id)
        if business_dna is None:
            raise BusinessDNANotFoundException()
        return business_dna

    async def upsert_business_dna(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> BusinessDNA:
        """Create the org's Business DNA profile if none exists, else update it.

        Args:
            organization_id: Organization the profile belongs to.
            actor_user_id: User performing the write, for the audit log.
            data: Field values, including the optional ``organization_name``.

        Returns:
            The created or updated ``BusinessDNA``.
        """
        # Pulled out first: this key belongs to `organizations.name`, not a
        # business_dna column, and its write happens last (see below).
        organization_name = data.pop("organization_name", None)

        existing = await self._repo.get_business_dna_by_organization_id(organization_id)

        if existing is not None:
            old_data = _snapshot(existing, data.keys())
            business_dna = await self._repo.update_business_dna(existing, data)
            action = "update"
        else:
            try:
                # A SAVEPOINT, not a full rollback: app.current_org_id was
                # set with SET LOCAL semantics (set_config(..., true)) by
                # the request-level dependency before this method ever
                # ran, i.e. it's scoped to the *outer* transaction. Rolling
                # back the whole transaction on conflict would silently
                # wipe that tenant context for every query for the rest of
                # the request — a nested transaction undoes only the
                # failed insert, leaving it intact.
                async with self._db.begin_nested():
                    business_dna = await self._repo.create_business_dna(
                        {**data, "organization_id": organization_id}
                    )
                old_data = None
                action = "create"
            except IntegrityError:
                # Lost a race with a concurrent create for the same org
                # (organization_id is UNIQUE) — fall back to update instead
                # of surfacing a raw 500. Same idiom Django's get_or_create()
                # documents for this exact race.
                existing = await self._repo.get_business_dna_by_organization_id(organization_id)
                old_data = _snapshot(existing, data.keys())
                business_dna = await self._repo.update_business_dna(existing, data)
                action = "update"

        # Organization name is written last, deliberately: it's a plain,
        # non-racy update, and running it after the business_dna branch
        # above is fully resolved means the rollback in the race-recovery
        # path (which rolls back this whole transaction) can never wipe out
        # a name change that already succeeded.
        if organization_name is not None:
            organization = await self._org_repo.get_organization_by_id(organization_id)
            await self._org_repo.update_organization(organization, {"name": organization_name})

        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type="business_dna",
            entity_id=business_dna.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return business_dna


class BusinessDNACoreValueService:
    """Business logic for creating, reading, updating, and deleting core values."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = BusinessDNACoreValueRepository(db)
        self._dna_repo = BusinessDNARepository(db)
        self._audit = AuditService(db)

    async def create_core_value(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> BusinessDNACoreValue:
        """Add a core value to the org's Business DNA profile.

        Args:
            organization_id: Organization the core value belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new core value.

        Returns:
            The newly created ``BusinessDNACoreValue``.

        Raises:
            BusinessDNANotFoundException: If the org hasn't created a
                Business DNA profile yet — a core value can't exist without
                a parent profile to attach to.
        """
        business_dna = await self._dna_repo.get_business_dna_by_organization_id(organization_id)
        if business_dna is None:
            raise BusinessDNANotFoundException()

        core_value = await self._repo.create_core_value(
            {**data, "organization_id": organization_id, "business_dna_id": business_dna.id}
        )
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="business_dna_core_value",
            entity_id=core_value.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return core_value

    async def list_core_values(self, organization_id: uuid.UUID) -> list[BusinessDNACoreValue]:
        """List every core value for the org's Business DNA profile.

        Args:
            organization_id: Organization to list core values for.

        Returns:
            The matching ``BusinessDNACoreValue`` rows, or an empty list —
            not a 404 — if no profile exists yet, since an empty collection
            isn't an error.
        """
        business_dna = await self._dna_repo.get_business_dna_by_organization_id(organization_id)
        if business_dna is None:
            return []
        return await self._repo.list_core_values_by_business_dna_id(business_dna.id)

    async def get_core_value_by_id(self, core_value_id: uuid.UUID) -> BusinessDNACoreValue:
        """Fetch a core value by id.

        Args:
            core_value_id: Id of the core value to fetch.

        Returns:
            The matching ``BusinessDNACoreValue``.

        Raises:
            BusinessDNACoreValueNotFoundException: If no core value with
                that id exists in the caller's org.
        """
        core_value = await self._repo.get_core_value_by_id(core_value_id)
        if core_value is None:
            raise BusinessDNACoreValueNotFoundException()
        return core_value

    async def update_core_value(
        self, core_value_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> BusinessDNACoreValue:
        """Apply a partial update to a core value and record an audit entry.

        Args:
            core_value_id: Id of the core value to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``BusinessDNACoreValue``.

        Raises:
            BusinessDNACoreValueNotFoundException: If no core value with
                that id exists in the caller's org.
        """
        core_value = await self.get_core_value_by_id(core_value_id)
        old_data = _snapshot(core_value, data.keys())
        core_value = await self._repo.update_core_value(core_value, data)
        await self._audit.log_action(
            organization_id=core_value.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="business_dna_core_value",
            entity_id=core_value.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return core_value

    async def delete_core_value(self, core_value_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        """Hard-delete a core value and record an audit entry.

        Args:
            core_value_id: Id of the core value to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Raises:
            BusinessDNACoreValueNotFoundException: If no core value with
                that id exists in the caller's org.
        """
        core_value = await self.get_core_value_by_id(core_value_id)
        old_data = _snapshot(core_value, BusinessDNACoreValue.__table__.columns.keys())
        await self._repo.delete_core_value(core_value)
        await self._audit.log_action(
            organization_id=core_value.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="business_dna_core_value",
            entity_id=core_value.id,
            changes={"old": old_data, "new": None},
        )
