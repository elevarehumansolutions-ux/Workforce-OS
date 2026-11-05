"""Asking the model to write the executive summary, and refusing numbers that are not in the facts.

08_DECISIONS.md 2026-10-21, question 10: the model writes from a fact sheet, our
code checks every number in what it wrote, one retry on a mismatch, and if the
second try is still wrong a plain fact-only summary is saved instead. An invented
figure is never shown on an investor-facing screen.
"""

import json
import logging
import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.enums import AIUsagePurpose, ModelTier
from app.modules.ai.llm import generate_structured

from .enums import SummarySource
from .summary_facts import plain_summary, unsupported_numbers

logger = logging.getLogger(__name__)

# The strong tier: a rarely-run, accuracy-sensitive job (see the decision).
SUMMARY_TIER = ModelTier.STRONG


class SummaryDraft(BaseModel):
    """What the model returns: the paragraph and nothing else."""

    text: str


SYSTEM_PROMPT = (
    "You write a short executive summary of a company's performance for its leadership. "
    "You are given a fact sheet as JSON. Write 3 to 5 plain sentences. Rules: "
    "(1) Use ONLY numbers that appear in the fact sheet, exactly as given. Never calculate a new number, "
    "never add numbers up, never round differently. "
    "(2) Talk about departments and patterns only. Never name or guess at any individual person. "
    "(3) Do not mention dates or quarter numbers; say 'this quarter' or 'the quarter so far' as the sheet does. "
    "(4) 'goals' means how a department's KPI results compare with target; 'punctuality' means how on time its tasks are. "
    "Keep them separate. A change is in points since the quarter before; a null change means there is no earlier figure. "
    "(5) If delays_by_reason is given, say where tasks were held back and why, using its counts. "
    "(6) Do not give advice or opinions; state what the facts show."
)


def build_prompt(sheet: dict, wrong_numbers: list[str] | None = None) -> str:
    """The user message: the fact sheet, plus a correction when a first try used numbers that are not facts."""
    prompt = "Fact sheet:\n" + json.dumps(sheet, indent=2)
    if wrong_numbers:
        prompt += (
            "\n\nYour previous answer used numbers that are not in the fact sheet: "
            + ", ".join(wrong_numbers)
            + ". Write it again using only numbers from the fact sheet."
        )
    return prompt


async def write_summary(
    db: AsyncSession, organization_id: uuid.UUID, sheet: dict
) -> tuple[str, SummarySource]:
    """The summary text and how it was written (model, or the plain fallback).

    Raises:
        LLMOutputError: The model gave no usable answer at all (refused or cut off).
            That fails the run; it is not covered by the plain fallback, which is for
            a model that answered with wrong numbers.
        anthropic.APIError: A transport problem; the Celery job retries it.
    """
    wrong_numbers = None
    for attempt in (1, 2):
        draft = await generate_structured(
            db,
            organization_id=organization_id,
            purpose=AIUsagePurpose.EXECUTIVE_SUMMARY_GENERATION,
            tier=SUMMARY_TIER,
            system=SYSTEM_PROMPT,
            prompt=build_prompt(sheet, wrong_numbers),
            output_type=SummaryDraft,
            max_tokens=1000,
        )
        text = draft.text.strip()
        wrong_numbers = unsupported_numbers(text, sheet)
        if text != "" and len(wrong_numbers) == 0:
            return text, SummarySource.AI
        logger.warning("Executive summary attempt %d used numbers not in the facts: %s", attempt, wrong_numbers)

    return plain_summary(sheet), SummarySource.PLAIN
