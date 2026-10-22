"""Tests for the workflow tables' own rules (M11 slice A).

These insert rows directly, so they prove the DATABASE refuses bad data
whatever the application code does.
"""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.tasks.models import Task
from app.modules.workflow.models import WorkflowInstance, WorkflowStep, WorkflowTemplate
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import _world


def _template(org_id, department_id, **changes) -> WorkflowTemplate:
    """A valid template row, with any field changed for the test at hand."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "department_id": uuid.UUID(department_id),
        "name": "Client Onboarding",
    }
    fields.update(changes)
    return WorkflowTemplate(**fields)


def _step(org_id, template_id, department_id, **changes) -> WorkflowStep:
    """A valid step row, with any field changed for the test at hand."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "workflow_template_id": template_id,
        "step_order": 1,
        "name": "Finance review",
        "department_id": uuid.UUID(department_id),
        "default_turnaround_hours": 24,
    }
    fields.update(changes)
    return WorkflowStep(**fields)


def _instance(org_id, template_id, **changes) -> WorkflowInstance:
    """A valid instance row (a running case), with any field changed for the test at hand."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "workflow_template_id": template_id,
        "subject": "Zenith Ltd",
    }
    fields.update(changes)
    return WorkflowInstance(**fields)


async def _refused(db_session, row) -> bool:
    """Whether the database refuses to store ``row``."""
    try:
        async with db_session.begin_nested():  # a savepoint, so one refusal doesn't spoil the test
            db_session.add(row)
            await db_session.flush()
    except IntegrityError:
        return True
    return False


async def _saved_template(db_session, org_id, department_id) -> WorkflowTemplate:
    """Store a valid template and return it, so a step or case can point at it."""
    template = _template(org_id, department_id)
    db_session.add(template)
    await db_session.flush()
    return template


@pytest.mark.asyncio
async def test_the_database_enforces_the_rules_of_a_step(client, monkeypatch, db_session):
    """A turnaround must be above zero (or empty), and the order starts at 1."""
    w = await _world(client, monkeypatch, "wf1")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    template = await _saved_template(db_session, org_id, w.dispatch)

    assert not await _refused(db_session, _step(org_id, template.id, w.sales))
    # No turnaround at all means "no deadline", which is allowed.
    assert not await _refused(
        db_session, _step(org_id, template.id, w.sales, step_order=2, default_turnaround_hours=None)
    )
    assert await _refused(db_session, _step(org_id, template.id, w.sales, default_turnaround_hours=0))
    assert await _refused(db_session, _step(org_id, template.id, w.sales, default_turnaround_hours=-5))
    assert await _refused(db_session, _step(org_id, template.id, w.sales, step_order=0))


@pytest.mark.asyncio
async def test_the_database_enforces_the_rules_of_a_case(client, monkeypatch, db_session):
    """Status takes three values; the finish time and cancel reason must match the status."""
    w = await _world(client, monkeypatch, "wf2")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    template = await _saved_template(db_session, org_id, w.dispatch)
    now = datetime.now(UTC)

    # A new case starts in progress with nothing else filled in.
    new_case = _instance(org_id, template.id)
    assert not await _refused(db_session, new_case)
    assert new_case.status == "in_progress"
    # A status that is not on the list.
    assert await _refused(db_session, _instance(org_id, template.id, status="paused"))
    # Completed, but no finish time.
    assert await _refused(db_session, _instance(org_id, template.id, status="completed"))
    # Still in progress, yet it has a finish time.
    assert await _refused(db_session, _instance(org_id, template.id, completed_at=now))
    # Cancelled with no reason.
    assert await _refused(db_session, _instance(org_id, template.id, status="cancelled"))
    # In progress, yet it has a cancel reason.
    assert await _refused(db_session, _instance(org_id, template.id, cancel_reason="Client withdrew"))
    # The proper finished and cancelled forms are fine.
    assert not await _refused(db_session, _instance(org_id, template.id, status="completed", completed_at=now))
    assert not await _refused(
        db_session, _instance(org_id, template.id, status="cancelled", cancel_reason="Client withdrew")
    )


@pytest.mark.asyncio
async def test_another_organization_cannot_see_the_workflow_rows(client, monkeypatch, db_session):
    """Row-level security covers all three new tables."""
    w = await _world(client, monkeypatch, "wf3")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    template = await _saved_template(db_session, org_id, w.dispatch)
    db_session.add(_step(org_id, template.id, w.sales))
    db_session.add(_instance(org_id, template.id))
    await db_session.flush()

    async def count_rows() -> tuple[int, int, int]:
        counts = []
        for model in (WorkflowTemplate, WorkflowStep, WorkflowInstance):
            result = await db_session.execute(select(func.count()).select_from(model))
            counts.append(result.scalar_one())
        return tuple(counts)

    mine = await count_rows()
    await set_org_context(db_session, uuid.uuid4())
    someone_elses = await count_rows()

    assert (mine, someone_elses) == ((1, 1, 1), (0, 0, 0))


@pytest.mark.asyncio
async def test_a_task_can_only_point_at_a_real_case_and_step(client, monkeypatch, db_session):
    """The two foreign keys M10 left out now exist: made-up ids are refused, real ones are fine."""
    w = await _world(client, monkeypatch, "wf4")
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    template = await _saved_template(db_session, org_id, w.dispatch)
    step = _step(org_id, template.id, w.sales)
    case = _instance(org_id, template.id)
    db_session.add_all([step, case])
    await db_session.flush()

    def task(**changes) -> Task:
        fields = {
            "organization_id": uuid.UUID(org_id),
            "department_id": uuid.UUID(w.sales),
            "title": "Finance review for Zenith Ltd",
        }
        fields.update(changes)
        return Task(**fields)

    assert not await _refused(db_session, task())  # a standalone task still needs neither
    assert not await _refused(db_session, task(workflow_instance_id=case.id, workflow_step_id=step.id))
    assert await _refused(db_session, task(workflow_instance_id=uuid.uuid4()))
    assert await _refused(db_session, task(workflow_step_id=uuid.uuid4()))
