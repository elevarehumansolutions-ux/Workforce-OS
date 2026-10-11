"""Tests for the task_blocks table's own rules (M10 slice E, step 1).

These insert rows directly, so they prove the DATABASE refuses bad data
whatever the application code does.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.tasks.models import TaskBlock
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import _task, _world


def _block(org_id, task_id, user_id, **changes) -> TaskBlock:
    """A valid block row, with any field changed for the test at hand."""
    fields = {
        "organization_id": uuid.UUID(org_id),
        "task_id": uuid.UUID(task_id),
        "blocked_by_user_id": uuid.UUID(user_id),
        "category": "awaiting_other_department",
        "reason": "Waiting for Finance to sign off",
    }
    fields.update(changes)
    return TaskBlock(**fields)


async def _refused(db_session, block: TaskBlock) -> bool:
    """Whether the database refuses to store ``block``."""
    try:
        async with db_session.begin_nested():  # a savepoint, so one refusal doesn't spoil the test
            db_session.add(block)
            await db_session.flush()
    except IntegrityError:
        return True
    return False


@pytest.mark.asyncio
async def test_the_database_enforces_the_rules_of_a_block(client, monkeypatch, db_session):
    """One open block per task, valid values only, and review fields that match the status."""
    w = await _world(client, monkeypatch, "e1")
    org_id = w.owner["organization"]["id"]
    user_id = w.owner["user"]["id"]
    task_id = (await _task(client, w.hr, w.dispatch, "Get sign-off")).json()["id"]
    await set_org_context(db_session, org_id)
    now = datetime.now(UTC)

    first_open_block = _block(org_id, task_id, user_id)
    assert not await _refused(db_session, first_open_block)

    # A second block while the first is still open.
    assert await _refused(db_session, _block(org_id, task_id, user_id))
    # A category that is not on the list.
    assert await _refused(db_session, _block(org_id, task_id, user_id, category="boredom", unblocked_at=now))
    # Unblocked before it was blocked.
    assert await _refused(
        db_session, _block(org_id, task_id, user_id, blocked_at=now, unblocked_at=now - timedelta(hours=1))
    )
    # Pending, yet someone is named as the reviewer.
    assert await _refused(
        db_session, _block(org_id, task_id, user_id, unblocked_at=now, reviewed_by_user_id=uuid.UUID(user_id))
    )
    # Approved, but nobody is named as the reviewer.
    assert await _refused(db_session, _block(org_id, task_id, user_id, unblocked_at=now, review_status="approved"))
    # A closed, properly reviewed block is fine (the open one above does not stop a closed one).
    reviewed = _block(
        org_id, task_id, user_id,
        blocked_at=now - timedelta(days=2), unblocked_at=now - timedelta(days=1),
        review_status="approved", reviewed_by_user_id=uuid.UUID(user_id), reviewed_at=now,
    )
    assert not await _refused(db_session, reviewed)


@pytest.mark.asyncio
async def test_another_organization_cannot_see_the_blocks(client, monkeypatch, db_session):
    """Row-level security covers the new table."""
    w = await _world(client, monkeypatch, "e2")
    org_id = w.owner["organization"]["id"]
    task_id = (await _task(client, w.hr, w.dispatch, "Get sign-off")).json()["id"]
    await set_org_context(db_session, org_id)
    db_session.add(_block(org_id, task_id, w.owner["user"]["id"]))
    await db_session.flush()

    mine = (await db_session.execute(select(func.count()).select_from(TaskBlock))).scalar_one()
    await set_org_context(db_session, uuid.uuid4())
    someone_elses = (await db_session.execute(select(func.count()).select_from(TaskBlock))).scalar_one()

    assert (mine, someone_elses) == (1, 0)
