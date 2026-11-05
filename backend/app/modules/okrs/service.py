"""Business logic for the OKR module.

Each service wraps its matching repository, adding not-found checks and
audit logging around plain CRUD. Services flush via the repository but
never commit — the router commits after a successful call, same convention
as the organization and Business DNA modules. Deletes are soft and are
refused while a KPI still measures the key result (``08_DECISIONS.md``
2026-11-05).
"""

import uuid

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import KeyResultNotFoundException, OKRNotFoundException, ResourceInUseException
from app.core.schemas import PaginationResponse
from app.modules.audit_and_notification.service import AuditService

from .models import KeyResult, OKR
from .repository import KeyResultRepository, OKRRepository


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


class OKRService:
    """Business logic for creating, reading, and updating OKRs."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = OKRRepository(db)
        self._key_result_repo = KeyResultRepository(db)
        self._audit = AuditService(db)

    async def create_okr(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> OKR:
        """Create an OKR for an organization and record an audit entry.

        Adding an objective is always additive (08_DECISIONS.md 2026-09-02)
        — existing OKRs are never touched by this, it's a plain insert.

        Args:
            organization_id: Organization the new OKR belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new OKR.

        Returns:
            The newly created ``OKR``.
        """
        okr = await self._repo.create_okr({**data, "organization_id": organization_id})
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="okr",
            entity_id=okr.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return okr

    async def get_okr_by_id(self, okr_id: uuid.UUID) -> OKR:
        """Fetch an OKR by id.

        Args:
            okr_id: Id of the OKR to fetch.

        Returns:
            The matching ``OKR``.

        Raises:
            OKRNotFoundException: If no non-deleted OKR with that id exists
                in the caller's org.
        """
        okr = await self._repo.get_okr_by_id(okr_id)
        if okr is None:
            raise OKRNotFoundException()
        return okr

    async def list_okrs(
        self,
        organization_id: uuid.UUID,
        department_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginationResponse:
        """List non-deleted OKRs for an organization.

        Args:
            organization_id: Organization to list OKRs for.
            department_id: If given, restrict results to this department.
            location_id: If given, restrict results to this location.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``OKR`` rows.
        """
        return await self._repo.list_okrs(
            organization_id, department_id, location_id, page, limit
        )

    async def update_okr(
        self, okr_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> OKR:
        """Apply a partial update to an OKR and record an audit entry.

        Args:
            okr_id: Id of the OKR to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``OKR``.

        Raises:
            OKRNotFoundException: If no non-deleted OKR with that id exists
                in the caller's org.
        """
        okr = await self.get_okr_by_id(okr_id)
        old_data = _snapshot(okr, data.keys())
        okr = await self._repo.update_okr(okr, data)
        await self._audit.log_action(
            organization_id=okr.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="okr",
            entity_id=okr.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return okr

    async def delete_okr(self, okr_id: uuid.UUID, actor_user_id: uuid.UUID) -> OKR:
        """Soft-delete an OKR together with its key results.

        Blocked, not cascaded, while any KPI still measures one of its key
        results: the KPI would be left pointing at something nobody can see.

        Args:
            okr_id: Id of the OKR to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``OKR``.

        Raises:
            OKRNotFoundException: If no non-deleted OKR with that id exists
                in the caller's org.
            ResourceInUseException: If a KPI still measures one of its key results.
        """
        okr = await self.get_okr_by_id(okr_id)
        key_results = await self._key_result_repo.list_all_key_results_of_okr(okr_id)

        kpi_count = await self._key_result_repo.count_active_kpis_on_key_results([kr.id for kr in key_results])
        if kpi_count > 0:
            raise ResourceInUseException(
                message=f"Cannot delete objective: {kpi_count} KPI(s) still measure its key results "
                "(remove or re-link them first)"
            )

        for key_result in key_results:
            old_key_result = _snapshot(key_result, KeyResult.__table__.columns.keys())
            await self._key_result_repo.soft_delete_key_result(key_result)
            await self._audit.log_action(
                organization_id=key_result.organization_id,
                actor_user_id=actor_user_id,
                action="delete",
                entity_type="key_result",
                entity_id=key_result.id,
                changes={"old": old_key_result, "new": None},
            )

        old_data = _snapshot(okr, OKR.__table__.columns.keys())
        okr = await self._repo.soft_delete_okr(okr)
        await self._audit.log_action(
            organization_id=okr.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="okr",
            entity_id=okr.id,
            changes={"old": old_data, "new": None},
        )
        return okr


class KeyResultService:
    """Business logic for creating, reading, and updating key results."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self._repo = KeyResultRepository(db)
        self._okr_repo = OKRRepository(db)
        self._audit = AuditService(db)

    async def create_key_result(
        self, okr_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> KeyResult:
        """Add a key result to an OKR and record an audit entry.

        Args:
            okr_id: OKR the new key result belongs to.
            actor_user_id: User performing the creation, for the audit log.
            data: Field values for the new key result.

        Returns:
            The newly created ``KeyResult``.

        Raises:
            OKRNotFoundException: If no non-deleted OKR with that id exists
                in the caller's org — a key result can't exist without a
                parent OKR to attach to.
        """
        okr = await self._okr_repo.get_okr_by_id(okr_id)
        if okr is None:
            raise OKRNotFoundException()

        key_result = await self._repo.create_key_result(
            {**data, "organization_id": okr.organization_id, "okr_id": okr_id}
        )
        await self._audit.log_action(
            organization_id=okr.organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="key_result",
            entity_id=key_result.id,
            changes={"old": None, "new": jsonable_encoder(data)},
        )
        return key_result

    async def get_key_result_by_id(self, key_result_id: uuid.UUID) -> KeyResult:
        """Fetch a key result by id.

        Args:
            key_result_id: Id of the key result to fetch.

        Returns:
            The matching ``KeyResult``.

        Raises:
            KeyResultNotFoundException: If no non-deleted key result with
                that id exists in the caller's org.
        """
        key_result = await self._repo.get_key_result_by_id(key_result_id)
        if key_result is None:
            raise KeyResultNotFoundException()
        return key_result

    async def list_key_results(
        self, okr_id: uuid.UUID, page: int = 1, limit: int = 20
    ) -> PaginationResponse:
        """List non-deleted key results for an OKR.

        Args:
            okr_id: OKR to list key results for.
            page: 1-indexed page number.
            limit: Maximum number of rows per page.

        Returns:
            A paginated response wrapping the matching ``KeyResult`` rows.

        Raises:
            OKRNotFoundException: If no non-deleted OKR with that id exists
                in the caller's org.
        """
        okr = await self._okr_repo.get_okr_by_id(okr_id)
        if okr is None:
            raise OKRNotFoundException()
        return await self._repo.list_key_results(okr_id, page, limit)

    async def update_key_result(
        self, key_result_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict
    ) -> KeyResult:
        """Apply a partial update to a key result and record an audit entry.

        Args:
            key_result_id: Id of the key result to update.
            actor_user_id: User performing the update, for the audit log.
            data: Mapping of field names to their new values.

        Returns:
            The updated ``KeyResult``.

        Raises:
            KeyResultNotFoundException: If no non-deleted key result with
                that id exists in the caller's org.
        """
        key_result = await self.get_key_result_by_id(key_result_id)
        old_data = _snapshot(key_result, data.keys())
        key_result = await self._repo.update_key_result(key_result, data)
        await self._audit.log_action(
            organization_id=key_result.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="key_result",
            entity_id=key_result.id,
            changes={"old": old_data, "new": jsonable_encoder(data)},
        )
        return key_result

    async def delete_key_result(self, key_result_id: uuid.UUID, actor_user_id: uuid.UUID) -> KeyResult:
        """Soft-delete a key result unless a KPI still measures it.

        Args:
            key_result_id: Id of the key result to delete.
            actor_user_id: User performing the deletion, for the audit log.

        Returns:
            The soft-deleted ``KeyResult``.

        Raises:
            KeyResultNotFoundException: If no non-deleted key result with
                that id exists in the caller's org.
            ResourceInUseException: If a KPI still measures it.
        """
        key_result = await self.get_key_result_by_id(key_result_id)

        kpi_count = await self._repo.count_active_kpis_on_key_results([key_result.id])
        if kpi_count > 0:
            raise ResourceInUseException(
                message=f"Cannot delete key result: {kpi_count} KPI(s) still measure it "
                "(remove or re-link them first)"
            )

        old_data = _snapshot(key_result, KeyResult.__table__.columns.keys())
        key_result = await self._repo.soft_delete_key_result(key_result)
        await self._audit.log_action(
            organization_id=key_result.organization_id,
            actor_user_id=actor_user_id,
            action="delete",
            entity_type="key_result",
            entity_id=key_result.id,
            changes={"old": old_data, "new": None},
        )
        return key_result
