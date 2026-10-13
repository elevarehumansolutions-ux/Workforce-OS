"""Tests for the in-process event bus (app/core/events.py).

The bus only passes the database session through, so these tests hand it a
plain marker object instead of a real session.
"""
import pytest

from app.core import events

SESSION = object()  # stands in for the publisher's database session


@pytest.fixture
def listeners_left_as_found():
    """Give each test an empty board, and put the real one back afterwards.

    When the whole suite runs, other tests have already started the app, and
    ``main.py`` has signed the real Workflow listeners up on the board. These
    tests publish toy notes, so the real listeners must not be on the board
    while they run.
    """
    saved = {name: list(found) for name, found in events._listeners.items()}
    events._listeners.clear()
    yield
    events._listeners.clear()
    events._listeners.update(saved)


@pytest.mark.asyncio
async def test_a_listener_is_told_with_the_session_and_the_details(listeners_left_as_found):
    """Chidi's task 123 completes: the listener gets the session and the facts."""
    told = []

    async def listener(db, **details):
        told.append((db, details))

    events.subscribe(events.TASK_COMPLETED, listener)
    await events.publish(events.TASK_COMPLETED, SESSION, task_id="123", organization_id="org-1")

    assert told == [(SESSION, {"task_id": "123", "organization_id": "org-1"})]


@pytest.mark.asyncio
async def test_only_listeners_of_that_event_are_told_and_all_of_them_in_order(listeners_left_as_found):
    """A cancelled-task listener hears nothing about a completion; two completion listeners run in sign-up order."""
    order = []

    async def first(db, **details):
        order.append("first")

    async def second(db, **details):
        order.append("second")

    async def only_for_cancellations(db, **details):
        order.append("cancelled-listener")

    events.subscribe(events.TASK_COMPLETED, first)
    events.subscribe(events.TASK_COMPLETED, second)
    events.subscribe(events.TASK_CANCELLED, only_for_cancellations)
    await events.publish(events.TASK_COMPLETED, SESSION, task_id="123")

    assert order == ["first", "second"]


@pytest.mark.asyncio
async def test_publishing_with_nobody_listening_does_nothing(listeners_left_as_found):
    """Task can announce even when Workflow has not signed up (or does not exist)."""
    events._listeners.clear()

    await events.publish(events.TASK_COMPLETED, SESSION, task_id="123")


@pytest.mark.asyncio
async def test_signing_up_twice_still_means_being_told_once(listeners_left_as_found):
    """The same function subscribed twice runs once per event, so the next task is never created twice."""
    calls = []

    async def listener(db, **details):
        calls.append(1)

    events.subscribe(events.TASK_COMPLETED, listener)
    events.subscribe(events.TASK_COMPLETED, listener)
    await events.publish(events.TASK_COMPLETED, SESSION, task_id="123")

    assert calls == [1]


@pytest.mark.asyncio
async def test_a_listener_that_fails_fails_the_publisher_and_stops_later_listeners(listeners_left_as_found):
    """Decision A: the error reaches the person who clicked, and nothing after the failure runs."""
    ran_after = []

    async def broken(db, **details):
        raise RuntimeError("Finance step is missing")

    async def after(db, **details):
        ran_after.append(1)

    events.subscribe(events.TASK_COMPLETED, broken)
    events.subscribe(events.TASK_COMPLETED, after)

    with pytest.raises(RuntimeError, match="Finance step is missing"):
        await events.publish(events.TASK_COMPLETED, SESSION, task_id="123")
    assert ran_after == []


@pytest.mark.asyncio
async def test_unsubscribing_stops_the_notes_and_is_harmless_when_not_subscribed(listeners_left_as_found):
    """A listener that left is not told; leaving twice is fine."""
    calls = []

    async def listener(db, **details):
        calls.append(1)

    events.subscribe(events.TASK_COMPLETED, listener)
    events.unsubscribe(events.TASK_COMPLETED, listener)
    events.unsubscribe(events.TASK_COMPLETED, listener)
    await events.publish(events.TASK_COMPLETED, SESSION, task_id="123")

    assert calls == []
