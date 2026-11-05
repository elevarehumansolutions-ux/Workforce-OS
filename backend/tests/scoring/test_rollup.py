"""Tests for the weighted average used by every roll-up (M12 slice C part 2). Pure logic."""
from decimal import Decimal

from app.modules.scoring.rollup import weighted_average

D = Decimal


def test_the_weights_decide_how_much_each_score_counts():
    """70% at weight 70 and 100% at weight 30 is 79.00, not the plain 85."""
    assert weighted_average([(D("70"), D("70")), (D("30"), D("100"))]) == D("79.00")


def test_a_missing_score_is_left_out_and_the_weights_are_rescaled_not_counted_as_zero():
    """Contract Paperwork has no data: Lead Follow-up's 67% stands alone, it is not pulled down to 47%."""
    assert weighted_average([(D("70"), D("67")), (D("30"), None)]) == D("67.00")


def test_no_scores_at_all_means_no_answer():
    """Nothing to average gives None (no data), never 0."""
    assert weighted_average([]) is None
    assert weighted_average([(D("70"), None), (D("30"), None)]) is None


def test_a_score_of_zero_is_a_real_score():
    """A KPI scored 0 is data: it pulls the average down, unlike a missing score."""
    assert weighted_average([(D("50"), D("0")), (D("50"), D("100"))]) == D("50.00")
    assert weighted_average([(D("50"), D("0"))]) == D("0.00")


def test_scores_above_100_are_allowed_for_a_team_that_beat_its_target():
    """A department's results can exceed 100."""
    assert weighted_average([(D("60"), D("112.5")), (D("40"), D("90"))]) == D("103.50")


def test_weights_that_add_up_to_zero_fall_back_to_a_plain_average():
    """No division by zero: two scores of weight 0 are simply averaged."""
    assert weighted_average([(D("0"), D("80")), (D("0"), D("60"))]) == D("70.00")


def test_the_result_is_rounded_half_up_to_two_decimals():
    """66.666... is 66.67; an exact half-cent (3.125) rounds up to 3.13."""
    assert weighted_average([(D("1"), D("100")), (D("2"), D("50"))]) == D("66.67")
    assert weighted_average([(D("16"), D("3.125"))]) == D("3.13")
