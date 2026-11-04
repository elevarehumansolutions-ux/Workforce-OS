"""Tests for the Company Performance Score rule (M12 slice F part 1). Pure: no database."""
from decimal import Decimal

from app.modules.scoring.rollup import company_headline


def d(text: str | None):
    """A Decimal, or None."""
    return None if text is None else Decimal(text)


def test_departments_are_weighted_by_their_revenue_share():
    """Sales 70 at 60%, Operations 90 at 30%, HR 100 at 10% give 79, not the plain average 86.67."""
    score, counted, plain = company_headline([(d("70"), d("60")), (d("90"), d("30")), (d("100"), d("10"))])

    assert (score, counted, plain) == (Decimal("79.00"), 3, False)


def test_a_department_without_a_share_is_left_out_and_not_counted():
    """HR has a result but no share: 2 of 3 counted, weights rescaled over the other two."""
    score, counted, plain = company_headline([(d("70"), d("60")), (d("90"), d("30")), (d("100"), None)])

    assert (score, counted, plain) == (Decimal("76.67"), 2, False)


def test_a_department_without_a_result_is_left_out_and_not_counted():
    """A department with a share but nothing measured is not a zero."""
    score, counted, plain = company_headline([(d("70"), d("60")), (None, d("40"))])

    assert (score, counted, plain) == (Decimal("70.00"), 1, False)


def test_with_no_shares_at_all_it_falls_back_to_a_plain_average():
    """Nobody has a share yet: the plain average of the results, and the answer says it was plain."""
    score, counted, plain = company_headline([(d("70"), None), (d("90"), None)])

    assert (score, counted, plain) == (Decimal("80.00"), 2, True)


def test_no_results_anywhere_is_no_data_not_zero():
    """Nothing measured: None, 0 counted."""
    assert company_headline([(None, d("60")), (None, None)]) == (None, 0, False)
    assert company_headline([]) == (None, 0, False)
