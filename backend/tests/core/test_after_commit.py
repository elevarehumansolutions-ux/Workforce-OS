"""run_after_commit: an action waits for the commit, and is dropped on a rollback.

Scenario: a request queues an email, then either saves (the email goes out) or fails and
rolls back (no email may go out for work that never happened).
"""
import pytest
from sqlalchemy import text

from app.core.after_commit import run_after_commit


@pytest.mark.asyncio
async def test_the_action_runs_only_after_the_commit(db_session):
    calls = []

    run_after_commit(db_session, lambda: calls.append("sent"))
    assert calls == []  # still inside the request: nothing yet

    await db_session.commit()

    assert calls == ["sent"]


@pytest.mark.asyncio
async def test_the_action_is_dropped_when_the_session_rolls_back(db_session):
    calls = []

    # A real request has run queries by the time it queues an email, so a transaction is open.
    await db_session.execute(text("SELECT 1"))
    run_after_commit(db_session, lambda: calls.append("sent"))
    await db_session.rollback()
    await db_session.commit()  # a later, unrelated commit must not bring it back

    assert calls == []


@pytest.mark.asyncio
async def test_each_action_runs_once_even_with_several_commits(db_session):
    calls = []

    run_after_commit(db_session, lambda: calls.append("first"))
    await db_session.commit()
    run_after_commit(db_session, lambda: calls.append("second"))
    await db_session.commit()
    await db_session.commit()

    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_a_failing_action_does_not_break_the_commit_or_the_others(db_session):
    calls = []

    def broken():
        raise RuntimeError("the message queue is down")

    run_after_commit(db_session, broken)
    run_after_commit(db_session, lambda: calls.append("still sent"))
    await db_session.commit()  # must not raise

    assert calls == ["still sent"]
