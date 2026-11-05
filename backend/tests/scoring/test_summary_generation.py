"""Tests for the model call, the number check, the retry and the fallback (M12 slice G). The model is faked."""
import uuid

import pytest

import app.modules.scoring.summary_generation as generation
from app.modules.ai.llm import LLMOutputError
from app.modules.scoring.enums import SummarySource
from app.modules.scoring.summary_facts import plain_summary
from app.modules.scoring.summary_generation import SummaryDraft, build_prompt, write_summary
from tests.scoring.test_summary_facts import sheet

GOOD = "The company scored 79, up 5 points, with punctuality at 81, down 2. Sales is at 70, down 5."
BAD = "The company scored 79, but Sales fell 30 points."  # 30 is not a fact


def fake_model(monkeypatch, *answers):
    """Replace the model call with one that returns the given texts in turn; returns the list of prompts it saw."""
    prompts = []
    remaining = list(answers)

    async def fake(db, **kwargs):
        prompts.append(kwargs["prompt"])
        answer = remaining.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SummaryDraft(text=answer)

    monkeypatch.setattr(generation, "generate_structured", fake)
    return prompts


@pytest.mark.asyncio
async def test_a_checked_answer_is_saved_as_written_by_the_model(monkeypatch):
    """First try uses only facts: one call, source ai."""
    prompts = fake_model(monkeypatch, GOOD)

    text, source = await write_summary(None, uuid.uuid4(), sheet())

    assert (text, source) == (GOOD, SummarySource.AI)
    assert len(prompts) == 1


@pytest.mark.asyncio
async def test_a_wrong_number_is_thrown_away_and_the_model_is_asked_once_more_naming_it(monkeypatch):
    """First try says 30 points: the second prompt names '30' and the good answer is kept."""
    prompts = fake_model(monkeypatch, BAD, GOOD)

    text, source = await write_summary(None, uuid.uuid4(), sheet())

    assert (text, source) == (GOOD, SummarySource.AI)
    assert len(prompts) == 2
    assert "not in the fact sheet: 30" in prompts[1] and "not in the fact sheet" not in prompts[0]


@pytest.mark.asyncio
async def test_two_wrong_answers_fall_back_to_the_plain_facts(monkeypatch):
    """Still wrong on the second try: the plain summary, source plain, exactly two calls (no third)."""
    prompts = fake_model(monkeypatch, BAD, BAD)

    text, source = await write_summary(None, uuid.uuid4(), sheet())

    assert source == SummarySource.PLAIN
    assert text == plain_summary(sheet())
    assert len(prompts) == 2


@pytest.mark.asyncio
async def test_an_empty_answer_counts_as_wrong(monkeypatch):
    """A blank paragraph is not saved; the retry's good answer is."""
    fake_model(monkeypatch, "   ", GOOD)

    text, source = await write_summary(None, uuid.uuid4(), sheet())

    assert (text, source) == (GOOD, SummarySource.AI)


@pytest.mark.asyncio
async def test_a_refusal_fails_the_run_instead_of_being_papered_over(monkeypatch):
    """No usable answer at all is an error for the job; the fallback is only for wrong numbers."""
    fake_model(monkeypatch, LLMOutputError("refused"))

    with pytest.raises(LLMOutputError):
        await write_summary(None, uuid.uuid4(), sheet())


def test_the_prompt_holds_the_facts_and_no_personal_names():
    """The model is shown the sheet as JSON; departments appear, and the sheet itself has no employee names."""
    prompt = build_prompt(sheet())

    assert '"Sales"' in prompt and '"goals_score": 70' in prompt
    assert "Chidi" not in prompt and "Tester" not in prompt
