"""Test helper for Stage 9 (scoring): run the nightly scoring job "as if" it were another date.

Scoring works in fiscal quarters, so a quarter only closes when a night runs after it ended.
Rather than wait three months, this runs the SAME nightly job the app runs (the real code, not a
copy) with a pretend "now". Only for a TEST company: every command asks you to type the
company's exact name, so it cannot be pointed at a real customer by accident.

Run inside the api container, from /app (the id comes from `SELECT id, name FROM organizations`):

    python scripts/admin/stage9_time_helper.py show     --org <id> --name "<exact name>"
    python scripts/admin/stage9_time_helper.py run      --org <id> --name "<exact name>" --on 2027-01-02
    python scripts/admin/stage9_time_helper.py unfreeze --org <id> --name "<exact name>" --quarter-start 2026-10-01

``run`` closes the quarter that ended before the date and refreshes the new one, and (for a
company older than the new quarter) sends the quarter-start KPI weight reminder. ``unfreeze``
re-opens a closed quarter so you can add data and close it again. Manual KPI results that HR
typed in are never touched by either.
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Run from /app as a plain script: make "app" importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select, text, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.core.model_registry  # noqa: E402, F401 - registers every model, as the app does
from app.core.config import settings  # noqa: E402
from app.modules.scoring import tasks as scoring_jobs  # noqa: E402
from app.modules.scoring.models import DepartmentScore, EmployeeKPIScore, ExecutiveSummary  # noqa: E402
from app.modules.tasks.periods import current_fiscal_quarter  # noqa: E402
from app.modules.tenancy_identity.models import Organization  # noqa: E402


async def open_company(db: AsyncSession, organization_id: uuid.UUID, typed_name: str) -> Organization:
    """Set the tenant context and return the company, but only if the typed name matches exactly."""
    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(organization_id)}
    )
    organization = (
        await db.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one_or_none()
    if organization is None:
        sys.exit("No company with that id (or the id is wrong).")
    if (organization.name or "") != typed_name:
        sys.exit(f"The name you typed does not match this company ({organization.name!r}). Nothing was changed.")
    return organization


def quarter_around(organization: Organization, moment: datetime) -> tuple[date, date]:
    """First and last day of the fiscal quarter containing ``moment``, on the company's clock."""
    start, end = current_fiscal_quarter(organization.fiscal_year_start_month, organization.timezone, moment)
    return start.date(), (end - timedelta(days=1)).date()


async def show(db: AsyncSession, organization: Organization) -> None:
    """Print the quarters around now and how many saved rows each has, frozen or not."""
    now = datetime.now(UTC)
    current_first, current_last = quarter_around(organization, now)
    previous_first, previous_last = quarter_around(
        organization, datetime.combine(current_first - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    )
    print(f"Company: {organization.name}  (created {organization.created_at:%Y-%m-%d}, fiscal year starts month "
          f"{organization.fiscal_year_start_month}, timezone {organization.timezone})")
    for label, first, last in (("previous", previous_first, previous_last), ("current", current_first, current_last)):
        total = await db.scalar(
            select(func.count()).select_from(DepartmentScore).where(
                DepartmentScore.organization_id == organization.id, DepartmentScore.period_start == first
            )
        )
        frozen = await db.scalar(
            select(func.count()).select_from(DepartmentScore).where(
                DepartmentScore.organization_id == organization.id,
                DepartmentScore.period_start == first,
                DepartmentScore.finalized_at.is_not(None),
            )
        )
        print(f"  {label:9} quarter {first} to {last}: {total} department rows, {frozen} frozen")


async def run(db: AsyncSession, organization: Organization, on: date) -> None:
    """Run the real nightly job as if it were ``on`` (01:00 UTC that day).

    This closes the quarter that ended before that day (once) and refreshes the new one; the
    quarter-start KPI weight reminder fires for a company older than the new quarter.
    """
    pretend_now = datetime.combine(on, datetime.min.time(), tzinfo=UTC) + timedelta(hours=1)
    result = await scoring_jobs.run_scoring_for_organization(db, organization.id, pretend_now)
    print(f"Ran the nightly job as if it were {pretend_now:%Y-%m-%d %H:%M} UTC: {result}")


async def unfreeze(db: AsyncSession, organization: Organization, quarter_start: date) -> None:
    """Re-open a closed quarter: clear its frozen marks so it can be closed again.

    Only the freeze is cleared; no number is deleted. Manual KPI results HR typed in are never
    touched (they live in another table). The next ``run`` recomputes and freezes it again.
    """
    for model in (EmployeeKPIScore, DepartmentScore, ExecutiveSummary):
        result = await db.execute(
            update(model)
            .where(model.organization_id == organization.id, model.period_start == quarter_start)
            .values(finalized_at=None)
        )
        print(f"  {model.__tablename__}: {result.rowcount} rows re-opened")
    await db.commit()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run scoring as if it were another date (TEST companies only).")
    parser.add_argument("command", choices=["show", "run", "unfreeze"])
    parser.add_argument("--org", required=True, help="the company's id")
    parser.add_argument("--name", required=True, help="the company's exact name, typed again as a safety check")
    parser.add_argument("--on", help="run: the pretend date, YYYY-MM-DD")
    parser.add_argument("--quarter-start", help="unfreeze: the first day of the quarter to re-open, YYYY-MM-DD")
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            organization = await open_company(db, uuid.UUID(args.org), args.name)
            if args.command == "show":
                await show(db, organization)
            elif args.command == "run":
                if not args.on:
                    sys.exit("run needs --on YYYY-MM-DD")
                await run(db, organization, date.fromisoformat(args.on))
            else:
                if not args.quarter_start:
                    sys.exit("unfreeze needs --quarter-start YYYY-MM-DD")
                await unfreeze(db, organization, date.fromisoformat(args.quarter_start))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
