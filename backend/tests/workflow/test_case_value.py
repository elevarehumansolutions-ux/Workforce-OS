"""The money view of a case (pure: no database).

Scenario: Zenith Ltd pays the company N2,000,000 to source a CFO, to be done by 30 November.
"""
from datetime import UTC, datetime
from decimal import Decimal

from app.modules.workflow.value import (
    AT_RISK,
    LOST,
    NONE,
    ON_TRACK,
    SECURED,
    case_value_status,
    value_amounts,
)

FEE = Decimal("2000000")
DEADLINE = datetime(2026, 11, 30, 17, 0, tzinfo=UTC)
EARLY = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
AFTER = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)


def _status(**overrides):
    fields = {
        "client_value": FEE,
        "deadline_at": DEADLINE,
        "status": "in_progress",
        "completed_at": None,
        "now": EARLY,
        "has_overdue_task": False,
    }
    fields.update(overrides)
    return case_value_status(**fields)


def test_no_figure_means_nothing_to_track():
    """A case without a figure (or a zero one) shows no money state at all."""
    assert _status(client_value=None) == NONE
    assert _status(client_value=Decimal(0)) == NONE


def test_a_running_case_with_nothing_late_is_on_track():
    """Running, before the deadline, no late task."""
    assert _status() == ON_TRACK


def test_an_overdue_task_puts_the_figure_at_risk():
    """One overdue task is enough."""
    assert _status(has_overdue_task=True) == AT_RISK


def test_missing_the_clients_deadline_while_running_is_a_loss():
    """30 November passed and the case is still running: the fee is lost."""
    assert _status(now=AFTER) == LOST
    assert _status(now=AFTER, has_overdue_task=True) == LOST


def test_cancelling_the_case_is_a_loss():
    """The client withdrew or the case was stopped: the figure is lost."""
    assert _status(status="cancelled") == LOST


def test_finishing_by_the_deadline_secures_the_figure():
    """Done on 20 November, deadline 30 November."""
    done = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    assert _status(status="completed", completed_at=done) == SECURED


def test_finishing_after_the_deadline_is_still_a_loss():
    """Done on 2 December: the deadline was missed."""
    assert _status(status="completed", completed_at=AFTER) == LOST


def test_exactly_on_the_deadline_is_not_late():
    """Same rule as tasks: late only once strictly past it."""
    assert _status(now=DEADLINE) == ON_TRACK
    assert _status(status="completed", completed_at=DEADLINE) == SECURED


def test_without_a_deadline_the_figure_is_never_lost_by_time():
    """No final deadline: it can be at risk, and lost only by cancelling."""
    assert _status(deadline_at=None, now=AFTER) == ON_TRACK
    assert _status(deadline_at=None, now=AFTER, has_overdue_task=True) == AT_RISK
    done = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
    assert _status(deadline_at=None, status="completed", completed_at=done) == SECURED
    assert _status(deadline_at=None, status="cancelled") == LOST


def test_the_figure_counts_in_one_bucket_only():
    """At risk and lost never double count."""
    assert value_amounts(FEE, AT_RISK) == (FEE, Decimal(0))
    assert value_amounts(FEE, LOST) == (Decimal(0), FEE)
    assert value_amounts(FEE, ON_TRACK) == (Decimal(0), Decimal(0))
    assert value_amounts(FEE, SECURED) == (Decimal(0), Decimal(0))
    assert value_amounts(None, AT_RISK) == (Decimal(0), Decimal(0))
