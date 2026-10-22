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
