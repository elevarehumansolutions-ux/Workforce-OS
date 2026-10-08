"""Tests for AISuggestionEditRequest — what a reviewer is allowed to send."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.ai.schemas import AISuggestionEditRequest


def test_an_empty_edit_is_rejected():
    """Adaeze submits a blank form: not an edit."""
    with pytest.raises(ValidationError):
        AISuggestionEditRequest()


def test_changing_just_one_field_is_enough():
    """She changes only the risk level; everything else stays the AI's."""
    edit = AISuggestionEditRequest(risk_level="medium")
    assert edit.risk_level == "medium"
    assert edit.criticality_type is None


def test_a_percentage_of_zero_is_a_real_value_not_an_empty_box():
    """0 is an answer ("this department gets nothing"), so `is None` — not falsiness — decides."""
    assert AISuggestionEditRequest(revenue_allocation_percentage=Decimal("0")).revenue_allocation_percentage == 0


def test_an_invented_risk_level_is_rejected():
    """Only real RiskLevel values pass."""
    with pytest.raises(ValidationError):
        AISuggestionEditRequest(risk_level="extremely spicy")


def test_a_blank_department_name_is_rejected():
    """A name of only spaces is trimmed to nothing and refused before the at-least-one check."""
    with pytest.raises(ValidationError):
        AISuggestionEditRequest(department_name="   ")
