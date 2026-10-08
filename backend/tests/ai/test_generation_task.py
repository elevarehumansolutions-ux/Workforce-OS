"""run_generation: the task's own logic, without a real Celery worker.

Scenario: it's 3am, and a message arrives with no logged-in user attached.
The task must set the tenant context itself before any query returns rows,
save what Claude (faked here) suggests, and commit — and never touch
another organization's rows.
"""
import uuid

import pytest
from sqlalchemy import select

from tests.ai.test_llm_generate_structured import _by_output_format, _fake_anthropic, _usage
from tests.ai.test_generate_critical_position_suggestions import _pick, _org_with_operations
from tests.conftest import register_verified_and_login
from app.modules.ai.models import AISuggestion
from app.modules.ai.schemas import CriticalPositionAnswer, MissingDepartmentAnswer, RevenueAllocationAnswer
from app.modules.ai.tasks import GENERATE_SUGGESTIONS_TASK, run_generation
from app.core.celery_app import celery

# _org_with_operations marks Operations critical, so every run also makes a
# revenue-allocation call (Operations is a candidate department there too,
# not just for critical_position), and every run makes a missing-department
# call regardless (that type has no "nothing to ask about" skip). Give both
# empty answers so these tests, which are about the critical_position path,
# aren't affected by either.
_NO_OTHER_SUGGESTION_TYPE_PICKS = {
    RevenueAllocationAnswer: RevenueAllocationAnswer(picks=[]),
    MissingDepartmentAnswer: MissingDepartmentAnswer(picks=[]),
}


def _critical_position_only(pick_handles):
    return _by_output_format(
        {
            CriticalPositionAnswer: CriticalPositionAnswer(picks=[_pick(h) for h in pick_handles]),
            **_NO_OTHER_SUGGESTION_TYPE_PICKS,
        }
    )


def test_the_task_name_is_the_one_org_structure_will_enqueue_by():
    """The constant is the contract; the registered name must match it exactly."""
    assert GENERATE_SUGGESTIONS_TASK in celery.tasks
    assert celery.tasks[GENERATE_SUGGESTIONS_TASK].name == GENERATE_SUGGESTIONS_TASK


@pytest.mark.asyncio
async def test_the_task_sets_its_own_tenant_context_and_commits(client, db_session, monkeypatch):
    """No request, no JWT — the task must announce which org it's acting for, then commit."""
    org_id, positions = await _org_with_operations(client, db_session, "task_gen1@example.com")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_critical_position_only(["P1"]))

    # A SAVEPOINT, so run_generation's own commit() only releases the savepoint —
    # it can't reach the fixture's outer transaction, which still rolls back at
    # teardown. Without this, the task's real commit() would leave this test's
    # rows permanently in the dev database (08_DECISIONS.md 2026-09-27).
    async with db_session.begin_nested():
        created_count = await run_generation(db_session, org_id)

    assert created_count == 1
    saved = (await db_session.scalars(select(AISuggestion))).one()
    assert saved.organization_id == org_id
    assert saved.position_id in positions.values()


@pytest.mark.asyncio
async def test_another_organizations_positions_are_never_touched(client, db_session, monkeypatch):
    """Running the task for org A must not see or affect org B's candidates."""
    org_a, _ = await _org_with_operations(client, db_session, "task_gen2a@example.com")
    org_b, _ = await _org_with_operations(client, db_session, "task_gen2b@example.com")
    _fake_anthropic(monkeypatch, usage=_usage(), parsed_output=_critical_position_only(["P1"]))

    async with db_session.begin_nested():
        await run_generation(db_session, org_a)

    rows = (await db_session.scalars(select(AISuggestion))).all()
    assert {row.organization_id for row in rows} == {org_a}
    assert org_b not in {row.organization_id for row in rows}


@pytest.mark.asyncio
async def test_an_org_with_nothing_to_ask_about_still_commits_cleanly(client, db_session, monkeypatch):
    """No critical department: critical_position/revenue_allocation skip Claude entirely.

    missing_department has no such skip (a brand-new org is exactly the
    case it exists for), so it still makes one real call here — faked, with
    an empty answer, so the org still ends up with nothing created.
    """
    owner = await register_verified_and_login(client, email="task_gen3@example.com")
    org_id = uuid.UUID(owner["organization"]["id"])
    _fake_anthropic(
        monkeypatch,
        usage=_usage(),
        parsed_output=_by_output_format({MissingDepartmentAnswer: MissingDepartmentAnswer(picks=[])}),
    )

    async with db_session.begin_nested():
        created_count = await run_generation(db_session, org_id)

    assert created_count == 0
