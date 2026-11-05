"""Tests for the marking rule (M12 slice B). Pure logic: no database, no clock.

The examples are the ones used when the rules were settled (08_DECISIONS.md
2026-10-21): Chidi's third quarter of 2026, July to September.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.model_registry import Task
from app.modules.scoring.marking import (
    Mark,
    TaskFacts,
    count_marks,
    mark_task,
    moment_it_counts,
    real_deadline,
    score_from_counts,
)
from app.modules.tasks.overdue import is_overdue

Q3_START = datetime(2026, 7, 1, tzinfo=UTC)
Q4_START = datetime(2026, 10, 1, tzinfo=UTC)  # also the first moment AFTER Q3
Q4_END = datetime(2027, 1, 1, tzinfo=UTC)
DAY = 86400  # seconds


def at(month: int, day: int, hour: int = 12, year: int = 2026) -> datetime:
    """A moment in UTC, noon by default."""
    return datetime(year, month, day, hour, tzinfo=UTC)


def final_mark_for_q3(facts: TaskFacts):
    """Mark a task for Q3 the way the final write at period close does (judged at the quarter's end)."""
    return mark_task(facts, Q3_START, Q4_START, now=Q4_START + timedelta(days=1))


def test_chidis_quarter_gives_three_on_time_two_late_one_not_done():
    """His six valid tasks and one cancelled one, marked exactly as the user's example."""
    tasks = {
        "A: two days early": TaskFacts("completed", due_at=at(7, 10), completed_at=at(7, 8)),
        "B: exactly on the deadline": TaskFacts("completed", due_at=at(7, 20), completed_at=at(7, 20)),
        "C: four days late": TaskFacts("completed", due_at=at(8, 5), completed_at=at(8, 9)),
        "D: five weeks late": TaskFacts("completed", due_at=at(8, 20), completed_at=at(9, 25)),
        "E: never done": TaskFacts("open", due_at=at(9, 15)),
        "F: blocked 3 days, approved": TaskFacts(
            "completed", due_at=at(9, 1), completed_at=at(9, 3),
            approved_blocked_seconds=3 * DAY, last_block_reviewed_at=at(9, 2),
        ),
        "G: cancelled": TaskFacts("cancelled", due_at=at(9, 10)),
    }

    marks = {name: final_mark_for_q3(facts) for name, facts in tasks.items()}

    assert marks == {
        "A: two days early": Mark.ON_TIME,
        "B: exactly on the deadline": Mark.ON_TIME,
        "C: four days late": Mark.LATE,
        "D: five weeks late": Mark.LATE,
        "E: never done": Mark.NOT_DONE,
        "F: blocked 3 days, approved": Mark.ON_TIME,
        "G: cancelled": None,
    }
    counts = count_marks(list(marks.values()))
    assert counts == (3, 2, 1)
    assert score_from_counts(*counts) == Decimal("66.67")


def test_the_exact_moments_of_the_deadline():
    """On the deadline is on time, one second after is late, and an open task is not late until the deadline has passed."""
    due = at(8, 1)

    on_the_dot = TaskFacts("completed", due_at=due, completed_at=due)
    one_second_late = TaskFacts("completed", due_at=due, completed_at=due + timedelta(seconds=1))
    open_task = TaskFacts("open", due_at=due)

    assert final_mark_for_q3(on_the_dot) == Mark.ON_TIME
    assert final_mark_for_q3(one_second_late) == Mark.LATE
    # Judged exactly at the deadline it is not late yet; one second later it is not done.
    assert mark_task(open_task, Q3_START, Q4_START, now=due) is None
    assert mark_task(open_task, Q3_START, Q4_START, now=due + timedelta(seconds=1)) == Mark.NOT_DONE


def test_cancelled_tasks_tasks_with_no_deadline_and_pending_blocks_are_left_out():
    """Decisions 1, 2b and 3: none of these three is marked, however the task ended."""
    cancelled = TaskFacts("cancelled", due_at=at(8, 1))
    no_deadline_done = TaskFacts("completed", due_at=None, completed_at=at(8, 1))
    no_deadline_open = TaskFacts("open", due_at=None)
    pending_and_done = TaskFacts(
        "completed", due_at=at(8, 1), completed_at=at(7, 30), has_pending_block=True
    )
    pending_and_open = TaskFacts("open", due_at=at(8, 1), has_pending_block=True)

    for facts in (cancelled, no_deadline_done, no_deadline_open, pending_and_done, pending_and_open):
        assert final_mark_for_q3(facts) is None


def test_the_period_is_decided_by_the_real_deadline_not_the_written_one():
    """Decision 2d: due 29 Sept, a 5-day block approved, so the real deadline is 4 Oct: it is marked in Q4, on time."""
    task = TaskFacts(
        "completed", due_at=at(9, 29), completed_at=at(10, 3),
        approved_blocked_seconds=5 * DAY, last_block_reviewed_at=at(9, 28),
    )

    assert real_deadline(task) == at(10, 4)
    assert mark_task(task, Q3_START, Q4_START, now=at(10, 2)) is None          # not on Q3's card
    assert mark_task(task, Q4_START, Q4_END, now=at(12, 31)) == Mark.ON_TIME   # on Q4's card


def test_a_block_reviewed_after_the_period_closed_is_marked_in_the_next_period():
    """Decision 3: the card for Q3 stays untouched; the task is marked in Q4 whichever way the review went."""
    # Rejected on 10 October: judged as if never blocked, due 25 Sept, never done.
    rejected = TaskFacts("open", due_at=at(9, 25), last_block_reviewed_at=at(10, 10))
    # Approved on 10 October for 5 days (real deadline 30 Sept), and it had been done on 29 Sept.
    approved = TaskFacts(
        "completed", due_at=at(9, 25), completed_at=at(9, 29),
        approved_blocked_seconds=5 * DAY, last_block_reviewed_at=at(10, 10),
    )

    assert moment_it_counts(rejected) == at(10, 10)
    assert moment_it_counts(approved) == at(10, 10)
    for facts in (rejected, approved):
        assert final_mark_for_q3(facts) is None
    assert mark_task(rejected, Q4_START, Q4_END, now=at(12, 31)) == Mark.NOT_DONE
    assert mark_task(approved, Q4_START, Q4_END, now=at(12, 31)) == Mark.ON_TIME


def test_a_review_inside_the_same_period_changes_nothing_about_the_period():
    """A block reviewed on 5 Sept for a task due 10 Sept still counts in Q3 on its real deadline."""
    task = TaskFacts(
        "completed", due_at=at(9, 10), completed_at=at(9, 9), last_block_reviewed_at=at(9, 5)
    )

    assert moment_it_counts(task) == at(9, 10)
    assert final_mark_for_q3(task) == Mark.ON_TIME


def test_work_finished_after_the_period_ended_does_not_count_in_that_period():
    """Due 20 Sept, finished on 5 Oct: Q3's final card says not done (it is judged at the quarter's end)."""
    task = TaskFacts("completed", due_at=at(9, 20), completed_at=at(10, 5))

    assert mark_task(task, Q3_START, Q4_START, now=at(10, 6)) == Mark.NOT_DONE


def test_a_task_that_is_not_due_yet_is_marked_only_once_it_is_done_or_late():
    """In a running period: an open task with a future deadline is not marked; one finished early is."""
    open_not_due = TaskFacts("open", due_at=at(9, 20))
    done_early = TaskFacts("completed", due_at=at(9, 20), completed_at=at(8, 15))

    assert mark_task(open_not_due, Q3_START, Q4_START, now=at(8, 20)) is None
    assert mark_task(done_early, Q3_START, Q4_START, now=at(8, 20)) == Mark.ON_TIME


def test_the_edges_of_a_period():
    """A deadline exactly at the start belongs to the period; exactly at the end belongs to the next one."""
    at_start = TaskFacts("open", due_at=Q3_START)
    at_end = TaskFacts("open", due_at=Q4_START)
    judged_later = Q4_END

    assert mark_task(at_start, Q3_START, Q4_START, now=judged_later) == Mark.NOT_DONE
    assert mark_task(at_end, Q3_START, Q4_START, now=judged_later) is None
    assert mark_task(at_end, Q4_START, Q4_END, now=judged_later) == Mark.NOT_DONE


def test_the_score_is_the_average_of_the_points_and_no_tasks_means_no_score():
    """Chidi's 66.67; nobody is None (no data), but missing every task is a real 0.00."""
    assert score_from_counts(3, 2, 1) == Decimal("66.67")
    assert score_from_counts(5, 0, 0) == Decimal("100.00")
    assert score_from_counts(2, 1, 0) == Decimal("83.33")
    assert score_from_counts(0, 1, 1) == Decimal("25.00")
    assert score_from_counts(0, 0, 4) == Decimal("0.00")
    assert score_from_counts(0, 0, 0) is None


def test_a_half_cent_rounds_up():
    """50 points over 16 tasks is 3.125, shown as 3.13 (half-up), not 3.12."""
    assert score_from_counts(0, 1, 15) == Decimal("3.13")


def test_counting_marks_skips_the_tasks_that_were_left_out():
    """None means left out, so it is not counted anywhere."""
    marks = [Mark.ON_TIME, None, Mark.LATE, Mark.ON_TIME, None, Mark.NOT_DONE]

    assert count_marks(marks) == (2, 1, 1)
    assert count_marks([]) == (0, 0, 0)
    assert count_marks([None, None]) == (0, 0, 0)


def test_not_done_agrees_with_the_task_modules_overdue_rule():
    """For an open task, "marked not done" must mean exactly what "overdue" means in the Task module.

    The real-deadline formula is written in two places (tasks/overdue.py and
    scoring/marking.py); this test fails if they ever drift apart.
    """
    deadline = at(8, 1)
    for approved_days in (0, 3):
        real = deadline + timedelta(days=approved_days)
        for judged_at in (real - timedelta(seconds=1), real, real + timedelta(seconds=1)):
            task = Task(status="open", due_at=deadline, approved_blocked_seconds=approved_days * DAY, blocked_since=None)
            facts = TaskFacts("open", due_at=deadline, approved_blocked_seconds=approved_days * DAY)

            marked_not_done = mark_task(facts, Q3_START, Q4_START, now=judged_at) == Mark.NOT_DONE

            assert marked_not_done == is_overdue(task, judged_at), (approved_days, judged_at)


def test_a_task_that_is_blocked_right_now_is_neither_overdue_nor_marked():
    """The Task module says a blocked task is never overdue; here its block is pending, so it is held out."""
    now = at(8, 20)
    blocked = Task(status="open", due_at=at(8, 1), approved_blocked_seconds=0, blocked_since=at(7, 30))
    facts = TaskFacts("open", due_at=at(8, 1), has_pending_block=True)

    assert is_overdue(blocked, now) is False
    assert mark_task(facts, Q3_START, Q4_START, now=now) is None
