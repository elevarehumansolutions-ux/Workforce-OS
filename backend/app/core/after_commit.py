"""Run something only once the database transaction has really been saved.

Why this exists: an email must not go out for work that is later undone. A service
asks for the email while it is still inside the request, but the request can still
fail and roll back after that. ``run_after_commit`` keeps the action until the
session commits, and forgets it if the session rolls back instead.
"""

import logging
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_WAITING = "actions_waiting_for_commit"
_LISTENING = "listening_for_commit"


def _run_waiting_actions(sync_session) -> None:
    actions = sync_session.info.pop(_WAITING, [])
    for action in actions:
        try:
            action()
        except Exception:
            # A failed side effect (for example the message queue being down) must never
            # turn an already saved request into an error for the person.
            logger.exception("An action that waited for the commit failed")


def _forget_waiting_actions(sync_session, *ignored) -> None:
    sync_session.info.pop(_WAITING, None)


def run_after_commit(db: AsyncSession, action: Callable[[], None]) -> None:
    """Call ``action()`` (a plain, quick function) after ``db`` commits.

    If the session rolls back instead, the action is dropped and never runs.
    """
    sync_session = db.sync_session
    if not sync_session.info.get(_LISTENING):
        # Listen once for the life of this session (a session lives for one request).
        event.listen(sync_session, "after_commit", _run_waiting_actions)
        # Fires on every rollback, including one that did not reach the database.
        event.listen(sync_session, "after_soft_rollback", _forget_waiting_actions)
        sync_session.info[_LISTENING] = True
    sync_session.info.setdefault(_WAITING, []).append(action)
