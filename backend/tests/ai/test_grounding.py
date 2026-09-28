"""Grounding: Claude's picks are translated back to real ids, invented ones dropped.

Scenario: Adaeze's org has 6 positions, shown to Claude as P1..P6. Claude
answers ["P2", "P9", "P4"]; P9 was never handed out, so it is dropped and
the reviewer sees suggestions for the two real positions only.
"""
import uuid

import pytest

from app.modules.ai.grounding import make_handles, resolve_handles
from app.modules.ai.llm import LLMOutputError

IDS = [uuid.uuid4() for _ in range(6)]
HANDLES = {f"P{n}": real_id for n, real_id in enumerate(IDS, start=1)}


def test_real_ids_get_short_numbered_handles():
    """P1..Pn, in order, each pointing at its real id — a lookup map, not text."""
    handles = make_handles(IDS[:3], "P")

    assert handles == {"P1": IDS[0], "P2": IDS[1], "P3": IDS[2]}


def test_an_invented_handle_is_dropped_and_the_real_ones_kept():
    """P9 doesn't exist: dropped, and reported. P2 and P4 come back as real ids."""
    result = resolve_handles(["P2", "P9", "P4"], HANDLES)

    assert result.ids == [IDS[1], IDS[3]]
    assert result.dropped == ["P9"]


def test_a_handle_listed_twice_is_kept_once_in_claudes_order():
    """Duplicates collapse; the first occurrence sets the position."""
    result = resolve_handles(["P3", "P1", "P3"], HANDLES)

    assert result.ids == [IDS[2], IDS[0]]


def test_messy_casing_and_spacing_still_resolve():
    """' p2 ' means P2 — leniency on formatting, not on facts."""
    result = resolve_handles([" p2 ", "p5"], HANDLES)

    assert result.ids == [IDS[1], IDS[4]]
    assert result.dropped == []


def test_exactly_half_invented_is_tolerated():
    """1 of 2 dropped is a typo-level problem, not a failed run."""
    result = resolve_handles(["P1", "P9"], HANDLES)

    assert result.ids == [IDS[0]]
    assert result.dropped == ["P9"]


def test_more_than_half_invented_fails_the_run():
    """2 of 3 invented points at a broken prompt, so the run is unusable."""
    with pytest.raises(LLMOutputError, match="2 of 3"):
        resolve_handles(["P1", "P8", "P9"], HANDLES)


def test_everything_invented_fails_the_run():
    """Nothing real at all is never a usable answer."""
    with pytest.raises(LLMOutputError):
        resolve_handles(["P8", "P9"], HANDLES)


def test_an_empty_answer_is_fine():
    """Claude finding nothing critical is a valid result, not a failure."""
    result = resolve_handles([], HANDLES)

    assert result.ids == []
    assert result.dropped == []
