"""Rolling several scores up into one, with their weights.

Plain logic, like ``marking.py``: no database, no clock. It is used for a
department's headline (its KPIs' results), and later for a person's overall
score and the company score.

The rule settled on 2026-10-21 (08_DECISIONS.md, M12 questions 5 and 6): only
the scores that EXIST are averaged, and their weights are rescaled so they add
up to 100. A score that is missing (no data) is left out, never counted as 0.
"""

from decimal import ROUND_HALF_UP, Decimal


def weighted_average(pairs: list[tuple[Decimal, Decimal | None]]) -> Decimal | None:
    """The weighted average of (weight, score) pairs, ignoring pairs with no score.

    Example: a KPI at 70% with weight 70 and a KPI at 100% with weight 30 give
    (70 x 70 + 100 x 30) / (70 + 30) = 79.00. If the second KPI had no score the
    answer is 70.00 (the weights are rescaled, the missing one is not a zero).
    If the weights of the scores that exist add up to 0, a plain average is used.

    Args:
        pairs: ``(weight, score)`` for each item; ``score`` is None for "no data".

    Returns:
        The average rounded to two decimals, or None if no pair has a score.
    """
    present = [(weight, score) for weight, score in pairs if score is not None]
    if not present:
        return None

    total_weight = sum(weight for weight, _ in present)
    if total_weight > 0:
        total = sum(weight * score for weight, score in present) / total_weight
    else:
        total = sum(score for _, score in present) / len(present)
    return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def company_headline(departments: list[tuple[Decimal | None, Decimal | None]]) -> tuple[Decimal | None, int, bool]:
    """The Company Performance Score from the departments' KPI results (question 6).

    Each department's result is weighted by its revenue share. A department with
    no result, or with no revenue share set, is LEFT OUT and not counted. If no
    department has a share, the score falls back to a plain average so the
    headline is not empty.

    Example: Sales 70 (share 60), Operations 90 (share 30), HR 100 (share 10) give
    (70 x 60 + 90 x 30 + 100 x 10) / 100 = 79. If HR had no share it would be
    left out: (70 x 60 + 90 x 30) / 90 = 76.67, counted as "2 of 3".

    Args:
        departments: ``(kpi_results_score, revenue_share)`` for every department;
            either may be None.

    Returns:
        ``(score, counted, used_plain_average)``; the score is None when no
        department has a result at all.
    """
    with_result = [(score, share) for score, share in departments if score is not None]

    shared = [(share, score) for score, share in with_result if share is not None]
    if len(shared) > 0:
        return weighted_average(shared), len(shared), False

    if len(with_result) > 0:
        every_one_equal = [(Decimal(1), score) for score, _ in with_result]
        return weighted_average(every_one_equal), len(with_result), True

    return None, 0, False
