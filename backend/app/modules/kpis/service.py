"""Business logic for the KPI module.

Wraps KPIRepository/KPIScoreRepository, adding weight-sum validation,
the group reconcile's create/update/delete diff, direction-aware score
calculation, and audit logging around plain CRUD. Flushes via the
repository but never commits — the router commits after a successful
call, same convention as every other module.
"""

from app.core.exceptions import KPIScorePeriodClosedException
from datetime import date
import decimal
import uuid
from app.core.exceptions import KPINotFoundException
from .schemas import KPIUpdate, KPIGroupUpdateRequest, KPIScoreCreate

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from .models import KPI, KPIScore
from .repository import KPIRepository, KPIScoreRepository
from .schemas import KPICreate
from app.core.exceptions import KPIWeightConflictException
from app.modules.audit_and_notification.service import AuditService, NotificationService


def _snapshot(instance, fields) -> dict:
    """Capture a JSON-safe snapshot of an ORM instance's current values.

    Used for the audit log's 'old' side of a before/after diff. Same
    helper as okrs/service.py and organization/service.py — small enough
    that sharing it isn't worth a cross-module import.

    Args:
        instance: The ORM instance to read attribute values from.
        fields: Names of the attributes/columns to include.

    Returns:
        A JSON-encodable dict mapping each field name to its current value.
    """
    return jsonable_encoder({field: getattr(instance, field, None) for field in fields})


class KPIService:
    """Business logic for creating, reading, updating, and scoring KPIs."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a session and its collaborators."""
        self._db = db
        self.kpi_repo = KPIRepository(db)
        self.score_repo = KPIScoreRepository(db)
        self._audit = AuditService(db)
        self.notification_service = NotificationService(db)

    async def create_kpi(
        self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, kpi: KPICreate
    ) -> KPI:
        """Create a KPI and record an audit entry.

        Rejects (409) if adding it would push its department/location
        group's weights over 100% — the group isn't required to sum to
        exactly 100 here, only not exceed it, so a list can still be
        built up one KPI at a time.

        Args:
            organization_id: Organization the new KPI belongs to.
            actor_user_id: User performing the creation, for the audit log.
            kpi: Field values for the new KPI.

        Returns:
            The newly created KPI.

        Raises:
            KPIWeightConflictException: If the group would exceed 100%.
        """
        # List all kpis under the department
        existing_total = await self.kpi_repo.sum_weights_for_group(
            kpi.department_id,
            kpi.location_id
        )

        new_total = existing_total + kpi.weight

        if new_total > 100:
            raise KPIWeightConflictException(
                f"KPI weights for this department must not exceed 100%. "
                f"Adding this KPI would bring the total to {new_total}%."
            )

        data = {**kpi.model_dump(), "organization_id": organization_id}

        created = await self.kpi_repo.create_kpi(data)
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="create",
            entity_type="kpi",
            entity_id=created.id,
            changes={"old": None, "new": jsonable_encoder(kpi.model_dump())},
        )
        return created
    
    async def update_kpi(
        self, kpi_id: uuid.UUID, actor_user_id: uuid.UUID, data: KPIUpdate
    ) -> KPI:
        """Apply a partial update to a KPI and record an audit entry.

        Only re-validates the weight group when ``weight`` is one of the
        fields being changed.

        Args:
            kpi_id: Id of the KPI to update.
            actor_user_id: User performing the update, for the audit log.
            data: Fields to update; anything left out is untouched.

        Returns:
            The updated KPI.

        Raises:
            KPINotFoundException: If no non-deleted KPI with that id
                exists in the caller's org.
            KPIWeightConflictException: If a changed weight would push
                the group over 100%.
        """
        kpi = await self.kpi_repo.get_kpi_by_id(kpi_id)
        if kpi is None:
            raise KPINotFoundException()


        update_data = data.model_dump(exclude_unset=True)

        if 'weight' in update_data:
            existing_total = await self.kpi_repo.sum_weights_for_group(
                kpi.department_id,
                kpi.location_id,
                kpi_id
            )

            new_total = existing_total + update_data["weight"]
            if new_total > 100:
                raise KPIWeightConflictException(
                    f"KPI weights for this department must not exceed 100%. "
                    f"Updating this KPI would bring the total to {new_total}%."
                )

        old_data = _snapshot(kpi, update_data.keys())
        updated = await self.kpi_repo.update_kpi(kpi, update_data)
        await self._audit.log_action(
            organization_id=updated.organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="kpi",
            entity_id=updated.id,
            changes={"old": old_data, "new": jsonable_encoder(update_data)},
        )
        return updated
    
    async def reconcile_kpis(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        department_id: uuid.UUID,
        location_id: uuid.UUID | None,
        request: KPIGroupUpdateRequest,
    ) -> list[KPI]:
        """Reconcile a department/location's whole KPI list in one call.

        An item with an ``id`` is updated, an item with no ``id`` is
        created, and an existing KPI whose id is missing from the
        submitted list is deleted — this is the only way to delete a
        KPI. Records one audit entry per create/update/delete performed,
        not one for the whole batch. The submitted list must sum to
        exactly 100.

        Args:
            organization_id: Organization the group belongs to.
            actor_user_id: User performing the reconcile, for the audit log.
            department_id: The group's department.
            location_id: The group's location, or ``None`` for the
                department-wide group.
            request: The whole desired KPI list for this group.

        Returns:
            The full resulting list of KPIs.

        Raises:
            KPIWeightConflictException: If the submitted list doesn't
                sum to exactly 100.
            KPINotFoundException: If a submitted item's id doesn't match
                any KPI currently in this group.
        """
        submitted_total = sum(item.weight for item in request.kpis)
        if submitted_total != 100:
            raise KPIWeightConflictException(
                f"KPI weights for this department must total 100%. "
                f"The submitted list totals {submitted_total}%."
            )

        existing = await self.kpi_repo.list_kpis_in_group(department_id, location_id)
        existing_by_id = {kpi.id: kpi for kpi in existing}
        submitted_ids = {item.id for item in request.kpis if item.id is not None}

        to_delete = [
            kpi for kpi_id, kpi in existing_by_id.items()
            if kpi_id not in submitted_ids
        ]

        for kpi in to_delete:
            old_data = _snapshot(kpi, KPI.__table__.columns.keys())
            deleted = await self.kpi_repo.soft_delete_kpi(kpi)
            await self._audit.log_action(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="delete",
                entity_type="kpi",
                entity_id=deleted.id,
                changes={"old": old_data, "new": None},
            )

        results = []
        for item in request.kpis:
            if item.id is None:
                data = {
                    **item.model_dump(exclude={"id"}),
                    "organization_id": organization_id,
                    "department_id": department_id,
                    "location_id": location_id,
                }
                created = await self.kpi_repo.create_kpi(data)
                await self._audit.log_action(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="create",
                    entity_type="kpi",
                    entity_id=created.id,
                    changes={"old": None, "new": jsonable_encoder(item.model_dump(exclude={"id"}))},
                )
                results.append(created)
            else:
                kpi = existing_by_id.get(item.id)
                if kpi is None:
                    raise KPINotFoundException(f"KPI {item.id} not found in this group")

                update_data = item.model_dump(exclude={"id"})
                old_data = _snapshot(kpi, update_data.keys())
                updated = await self.kpi_repo.update_kpi(kpi, update_data)
                await self._audit.log_action(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="update",
                    entity_type="kpi",
                    entity_id=updated.id,
                    changes={"old": old_data, "new": jsonable_encoder(update_data)},
                )
                results.append(updated)

        return results
    
    @staticmethod
    def calculate_score_percentage(
        actual_value: decimal.Decimal | None,
        target_value: decimal.Decimal | None,
        is_inverse: bool,
    ) -> decimal.Decimal | None:
        """Work out actual-vs-target as a percentage, honoring KPI direction.

        Returns ``None`` whenever the ratio genuinely can't be computed — no
        target set, no actual recorded, or the denominator would be zero
        (e.g. an inverse KPI hitting a perfect 0) — rather than fabricating
        a number. Matches how dashboards elsewhere show "N/A" instead of a
        guessed value when a ratio is undefined.
        """
        if actual_value is None or target_value is None:
            return None
        
        if is_inverse:
            if actual_value == 0:
                return None
            
            return (target_value / actual_value) * 100
        
        if target_value == 0:
            return None
        
        return (actual_value / target_value) * 100
    
    async def upsert_score(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        kpi_id: uuid.UUID,
        data: KPIScoreCreate,
    ) -> KPIScore:
        """Upsert the current, still-open period's actual value for a KPI.

        Repeatable while the period is still open, so progress is
        visible mid-quarter, not just at close — each call updates the
        same row and records its own audit entry (create the first
        time, update after that). 409 once ``period_end`` has passed.

        Args:
            organization_id: Organization the KPI belongs to.
            actor_user_id: User performing the upsert, for the audit log.
            kpi_id: Id of the KPI this score is for.
            data: The period and its actual value.

        Returns:
            The created or updated score, with ``score_percentage``
            computed server-side.

        Raises:
            KPINotFoundException: If no non-deleted KPI with that id
                exists in the caller's org.
            KPIScorePeriodClosedException: If ``period_end`` has already
                passed.
        """
        kpi = await self.kpi_repo.get_kpi_by_id(kpi_id)
        if kpi is None:
            raise KPINotFoundException()

        if data.period_end < date.today():
            raise KPIScorePeriodClosedException()

        score_percentage = KPIService.calculate_score_percentage(
            data.actual_value, kpi.target_value, kpi.is_inverse
        )

        existing_score = await self.score_repo.get_score_for_period(
            kpi_id, data.period_start, data.period_end
        )

        if existing_score is None:
            created = await self.score_repo.create_kpi_score({
                "organization_id": organization_id,
                "kpi_id": kpi_id,
                "period_start": data.period_start,
                "period_end": data.period_end,
                "actual_value": data.actual_value,
                "score_percentage": score_percentage,
            })
            await self._audit.log_action(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="create",
                entity_type="kpi_score",
                entity_id=created.id,
                changes={
                    "old": None,
                    "new": jsonable_encoder(
                        {"actual_value": data.actual_value, "score_percentage": score_percentage}
                    ),
                },
            )
            return created

        old_data = _snapshot(existing_score, ("actual_value", "score_percentage"))
        updated = await self.score_repo.update_score(
            existing_score,
            {"actual_value": data.actual_value, "score_percentage": score_percentage},
        )
        await self._audit.log_action(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="update",
            entity_type="kpi_score",
            entity_id=updated.id,
            changes={
                "old": old_data,
                "new": jsonable_encoder(
                    {"actual_value": data.actual_value, "score_percentage": score_percentage}
                ),
            },
        )
        return updated
            
        

        