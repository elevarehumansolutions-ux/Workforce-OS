"""The fact sheet behind the executive summary, the number check, and the plain fallback.

Plain logic with no database and no model call (08_DECISIONS.md 2026-10-21,
question 10). The model only ever sees the fact sheet, which holds NO personal
names (departments only), no dates and no ids, so it cannot mention a person it
was never told about. Every number the model writes is then checked against the
numbers in the sheet; a summary with a number that is not in it is never saved.
"""

import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal

# Below this many valid tasks in the period the summary is not written at all (question 11).
MIN_VALID_TASKS_FOR_SUMMARY = 10


def number(value: Decimal | None) -> int | float | None:
    """A score as the plain number the model sees: one decimal, and no ".0" when whole.

    Example: Decimal("66.67") becomes 66.7 and Decimal("79.00") becomes 79.
    """
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def change(now: Decimal | None, before: Decimal | None) -> int | float | None:
    """Points gained (positive) or lost (negative) since the earlier period; None if either is missing."""
    if now is None or before is None:
        return None
    return number(now - before)


def build_fact_sheet(
    period_is_closed: bool,
    company: dict,
    departments: list[dict],
    delays: list[dict],
) -> dict:
    """The fact sheet, in the exact shape the model is shown.

    Args:
        period_is_closed: Whether the period is over (final) or still running ("so far").
        company: Company-level numbers: ``headline``, ``headline_change``,
            ``departments_counted``, ``departments_total``, ``punctuality``,
            ``punctuality_change``, ``tasks_on_time``, ``tasks_late``, ``tasks_not_done``.
        departments: One dict per department: ``name``, ``goals_score``,
            ``goals_change``, ``punctuality``, ``punctuality_change``.
        delays: One dict per department and reason: ``department``, ``reason``,
            ``held_back_tasks``.

    Nothing here identifies a person.
    """
    return {
        "period": "the quarter that has ended" if period_is_closed else "the quarter so far",
        "company": company,
        "departments": departments,
        "delays_by_reason": delays,
    }


def fingerprint(sheet: dict) -> str:
    """A hash of the fact sheet: if it has not changed since last week, no new summary is needed."""
    text = json.dumps(sheet, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- the number check

# A number in running text: "79", "66.7", "1,200". Not the digit inside a word or a code like "Q3".
_NUMBER_IN_TEXT = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _collect_numbers(value, found: set) -> None:
    """Every number anywhere in the fact sheet (and its absolute value, since "down 5" says 5 for -5)."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        found.add(Decimal(str(abs(value))).normalize())
    elif isinstance(value, str):
        # A name such as "Unit 7" legitimately contains a digit.
        for written in _NUMBER_IN_TEXT.findall(value):
            found.add(Decimal(written.replace(",", "")).normalize())
    elif isinstance(value, dict):
        for item in value.values():
            _collect_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_numbers(item, found)


def numbers_in(text: str) -> list[str]:
    """The numbers written in a text, as they appear (commas removed)."""
    return [match.replace(",", "") for match in _NUMBER_IN_TEXT.findall(text)]


def unsupported_numbers(text: str, sheet: dict) -> list[str]:
    """The numbers in ``text`` that are NOT in the fact sheet. Empty means the text is safe to save.

    "79", "79.0" and "79%" all count as the number 79.
    """
    allowed = set()
    _collect_numbers(sheet, allowed)

    wrong = []
    for written in numbers_in(text):
        if Decimal(written).normalize() not in allowed:
            wrong.append(written)
    return wrong


# ---- the plain fallback

def _with_change(score, points) -> str:
    """'70 (-5)', or just '70' when there is no earlier figure to compare with."""
    if points is None:
        return str(score)
    sign = "+" if points > 0 else ""
    return f"{score} ({sign}{points})"


def plain_summary(sheet: dict) -> str:
    """A fact-only summary with no model wording, used when the model's numbers cannot be trusted.

    Example: "Company score 79 (+5); punctuality 81 (-2). Operations: goals 90 (+12), punctuality 88.
    Sales: goals 70 (-5), punctuality 86."
    """
    company = sheet["company"]
    parts = []

    opening = []
    if company["headline"] is not None:
        opening.append("Company score " + _with_change(company["headline"], company["headline_change"]))
    if company["punctuality"] is not None:
        opening.append("punctuality " + _with_change(company["punctuality"], company["punctuality_change"]))
    if opening:
        parts.append("; ".join(opening) + ".")

    for department in sheet["departments"]:
        pieces = []
        if department["goals_score"] is not None:
            pieces.append("goals " + _with_change(department["goals_score"], department["goals_change"]))
        if department["punctuality"] is not None:
            pieces.append("punctuality " + _with_change(department["punctuality"], department["punctuality_change"]))
        if pieces:
            parts.append(department["name"] + ": " + ", ".join(pieces) + ".")

    return " ".join(parts)
