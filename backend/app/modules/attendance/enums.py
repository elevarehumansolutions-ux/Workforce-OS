"""Enumerations used by the attendance module's models and schemas."""

from enum import Enum


class AttendanceClosedBy(str, Enum):
    """Who ended an attendance record.

    ``EMPLOYEE``: the person clocked out themselves, so the clock-out time is
    a fact. ``SYSTEM``: nobody did, and the nightly auto-close job ended the
    record at the organization's midnight cutoff — that time is a guess, and
    this value is how anything downstream (scoring, payroll later) can tell.
    See 08_DECISIONS.md 2026-10-01.
    """

    EMPLOYEE = "employee"
    SYSTEM = "system"
