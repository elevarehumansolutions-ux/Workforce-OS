"""A tiny in-process notice board: one module announces, others react.

The announcing module does not know who is listening.

Scenario: Chidi completes his Marketing task. The Task module pins a note,
"task 123 was completed", and moves on. The Workflow module has asked to be
told about such notes, so it creates the next step's task. Task never imports
Workflow, which keeps the rule "Workflow calls Task, Task never calls
Workflow" (08_DECISIONS.md 2026-10-12).

Listeners run inside the publisher's own database transaction and are
awaited one after another. If a listener raises, the error goes straight back
to whoever triggered the event, and the transaction is rolled back with it:
completing a task and creating the next one succeed or fail together.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

# Event names. Always use these constants, never a typed-out string.
TASK_COMPLETED = "task.completed"
TASK_CANCELLED = "task.cancelled"

# A listener is an async function: ``async def listener(db, **details)``.
Listener = Callable[..., Awaitable[None]]

_listeners: dict[str, list[Listener]] = {}


def subscribe(event_name: str, listener: Listener) -> None:
    """Ask to be told whenever ``event_name`` is published.

    Subscribing the same function to the same event twice is ignored, so a
    module can safely register at startup more than once.

    Args:
        event_name: One of the event name constants above.
        listener: ``async def listener(db, **details)`` to call on each event.
    """
    listeners = _listeners.setdefault(event_name, [])
    if listener not in listeners:
        listeners.append(listener)


def unsubscribe(event_name: str, listener: Listener) -> None:
    """Stop being told about ``event_name``. Does nothing if not subscribed.

    Mostly for tests, which must not leave their listeners behind.
    """
    listeners = _listeners.get(event_name, [])
    if listener in listeners:
        listeners.remove(listener)


async def publish(event_name: str, db: AsyncSession, **details) -> None:
    """Tell every listener of ``event_name`` what happened, and wait for them.

    The publisher's database session is passed along so the listeners do
    their work in the same transaction. A listener's exception is not caught
    here: it reaches the publisher, which lets the whole request fail.

    Args:
        event_name: One of the event name constants above.
        db: The publisher's session (same transaction as the publisher).
        **details: Facts about the event, such as ``task_id`` and ``organization_id``.
    """
    for listener in list(_listeners.get(event_name, [])):
        await listener(db, **details)
