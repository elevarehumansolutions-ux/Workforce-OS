"""Most Improved: the top three by change in points (08_DECISIONS.md 2026-10-21, question 7).

Plain logic with no database. It is a recognition list, not a verdict: each entry
carries the scores and task counts of BOTH periods so a reader sees how it was
earned (for example "Ada: 40 to 70, on 20 tasks").
"""

from decimal import Decimal

# A person or department needs at least this many valid tasks in BOTH periods to be listed.
MIN_VALID_TASKS = 10
HOW_MANY_LISTED = 3


class Candidate:
    """A person or department with its score and task count in two periods.

    Attributes:
        key: The employee or department id.
        previous_score: Score in the earlier period, or None for no data.
        previous_tasks: Valid tasks behind that score.
        current_score: Score in the asked period, or None for no data.
        current_tasks: Valid tasks behind that score.
    """

    def __init__(
        self,
        key,
        previous_score: Decimal | None,
        previous_tasks: int,
        current_score: Decimal | None,
        current_tasks: int,
    ):
        """Store the two periods' figures."""
        self.key = key
        self.previous_score = previous_score
        self.previous_tasks = previous_tasks
        self.current_score = current_score
        self.current_tasks = current_tasks

    def change_in_points(self) -> Decimal:
        """Current score minus previous score. Only call when both exist."""
        return self.current_score - self.previous_score

    def qualifies(self) -> bool:
        """Whether there is enough evidence to list this candidate.

        Both scores must exist, both periods need at least ``MIN_VALID_TASKS``
        valid tasks, and the score must actually have gone UP (this is a list of
        improvements).
        """
        if self.previous_score is None or self.current_score is None:
            return False
        if self.previous_tasks < MIN_VALID_TASKS or self.current_tasks < MIN_VALID_TASKS:
            return False
        return self.change_in_points() > 0


def _biggest_gain_first(candidate: Candidate) -> tuple:
    """Sort key: biggest gain first; on a tie the one with more current tasks (more evidence)."""
    return (-candidate.change_in_points(), -candidate.current_tasks)


def most_improved(candidates: list[Candidate]) -> list[Candidate]:
    """All qualifying candidates, biggest gain first. The caller takes as many as it can list.

    Returns every qualifying candidate rather than just three, because the caller
    may need to skip one (for example a person who has since been deleted) and
    still list three.
    """
    qualifying = [candidate for candidate in candidates if candidate.qualifies()]
    return sorted(qualifying, key=_biggest_gain_first)
