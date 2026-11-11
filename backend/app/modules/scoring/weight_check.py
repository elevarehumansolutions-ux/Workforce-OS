"""The quarter-start check that every department's KPI weights add up to 100%.

While KPIs are being drafted their weights may total less than 100 (08_DECISIONS.md 2026-11-10),
and scoring copes: it rescales the weights that exist, so a department at 70% is still scored
fairly. But a department at 70% means 30% of its purpose is not measured, and the owner should
know when a scoring quarter begins. So on the nightly run of a new quarter, each HR administrator
gets ONE notification per department that is short, and the scoring carries on regardless: this
is a reminder, never a block. Never commits.
"""

import decimal
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.models import Notification
from app.modules.audit_and_notification.service import NotificationService
from app.modules.kpis.repository import KPIRepository
from app.modules.organization.repository import DepartmentRepository
from app.modules.tenancy_identity.enums import MembershipRole
from app.modules.tenancy_identity.service import MembershipService

WEIGHT_CHECK_TITLE = "A department's KPI weights are not at 100%"
# Its own link type: "department" already means "open that department's tasks" on the Notifications
# screen. This one opens the KPIs screen for the department (link_id is the department's id).
WEIGHT_CHECK_LINK_TYPE = "department_kpis"


class KpiWeightCheck:
    """Tell HR which departments start the quarter with KPI weights short of 100%."""

    def __init__(self, db: AsyncSession):
        """Initialize with an RLS-scoped session."""
        self._db = db
        self._departments = DepartmentRepository(db)
        self._kpis = KPIRepository(db)
        self._notifications = NotificationService(db)
        self._memberships = MembershipService(db)

    async def _already_told_this_quarter(self, department_id: uuid.UUID, quarter_start: datetime) -> bool:
        """True when this department's reminder was already sent since the quarter began."""
        count = await self._db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.title == WEIGHT_CHECK_TITLE,
                Notification.link_type == WEIGHT_CHECK_LINK_TYPE,
                Notification.link_id == department_id,
                Notification.created_at >= quarter_start,
            )
        )
        return bool(count)

    async def run(self, organization_id: uuid.UUID, quarter_start: datetime) -> int:
        """Send the reminders for a quarter; returns how many departments were reported.

        Only a department that HAS KPIs and whose weights total less than 100 is reported (one
        with no KPIs at all is a different matter: it simply shows "no KPIs"). Running again the
        same quarter sends nothing new, so the nightly job can call this every night.
        """
        recipients = await self._memberships.list_active_user_ids_by_role(
            organization_id, MembershipRole.HR_ADMINISTRATOR.value
        )
        if not recipients:
            return 0

        reported = 0
        page = 1
        while True:
            result = await self._departments.list_departments(organization_id, page, 100)
            for department in result.data:
                total = await self._kpis.sum_weights_for_group(department.id, None)
                if total <= 0 or total >= 100:
                    continue
                if await self._already_told_this_quarter(department.id, quarter_start):
                    continue
                unmeasured = decimal.Decimal(100) - total
                await self._notifications.notify(
                    organization_id=organization_id,
                    recipient_user_ids=recipients,
                    category=NotificationCategory.SYSTEM,
                    title=WEIGHT_CHECK_TITLE,
                    body=(
                        f"{department.name}: its KPIs add up to {total.normalize():f}%, so "
                        f"{unmeasured.normalize():f}% of what it is for is not measured this quarter. "
                        "Scores are still worked out on the KPIs it has. Give the remaining weight "
                        "to a KPI, or add one."
                    ),
                    link_type=WEIGHT_CHECK_LINK_TYPE,
                    link_id=department.id,
                )
                reported += 1
            if not result.pagination.has_next:
                return reported
            page += 1
