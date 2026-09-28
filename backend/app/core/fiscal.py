"""Fiscal-calendar date math.

Shared across modules that key off an organization's
``fiscal_year_start_month`` (e.g. AI Suggestions' rejected-suggestion
quarterly suppression, the Quarterly Objective Review).
"""

from datetime import datetime, timedelta


def get_fiscal_quarter_start(fiscal_year_start_month: int, reference: datetime) -> datetime:
    """Get the start of the fiscal quarter containing ``reference``.

    Trusts ``fiscal_year_start_month`` is already a valid 1-12 value - 
    ``organizations.fiscal_year_start_month`` enforces this with a CHECK
    constraint at the database level, so this function doesn't re-validate
    a caller's own already-guaranteed data.

    Args:
        fiscal_year_start_month: The organization's fiscal year start
            month (1-12, e.g. 4 for an April-start fiscal year).
        reference: The timestamp to find the containing fiscal quarter
            for. Its tzinfo is preserved on the returned value.
    
    Returns:
        A timestamp at midnight on the first day of the fiscal quarter
        containing ``reference``, in the same timezone as ``reference``.
    """
    months_since_fiscal_start = (reference.month - fiscal_year_start_month) % 12
    quarter_start_month = (
        (fiscal_year_start_month - 1 + (months_since_fiscal_start // 3) * 3) % 12
    ) + 1
    quarter_start_year = (
        reference.year if quarter_start_month <= reference.month else reference.year - 1
    )
    return datetime(
        quarter_start_year, quarter_start_month, 1, tzinfo=reference.tzinfo
    )


def is_due_for_quarterly_review(
    fiscal_year_start_month: int, now: datetime, lookback: timedelta
) -> bool:
    """Whether this org's fiscal quarter turned over within the last ``lookback`` window.

    Backs the Quarterly Objective Review Beat job (08_DECISIONS.md
    2026-09-27): a org whose quarter just started gets suggestion
    generation re-run even with zero organic activity that quarter — the
    scheduled half of "recurring, not one-time" (01_REQUIREMENTS.md
    workflow #4), event triggers being the other half.

    ``lookback`` should exceed the Beat schedule's own interval (e.g. a
    daily schedule paired with a ~26h lookback) so a boundary that falls
    right between two runs is never missed — at the cost of occasionally
    re-including an org that was already caught by the previous run.
    Harmless: the generation task this feeds is fully idempotent.

    Args:
        fiscal_year_start_month: The organization's fiscal year start month (1-12).
        now: The current time to check against.
        lookback: How far back "just turned over" reaches.

    Returns:
        True if the org's current fiscal quarter started within
        ``lookback`` of ``now``.
    """
    return now - get_fiscal_quarter_start(fiscal_year_start_month, now) < lookback

