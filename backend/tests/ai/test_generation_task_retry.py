"""The task's retry policy: what gets retried, and what fails outright.

Scenario: Claude's connection drops mid-call. Celery should try again on its
own. But if Claude answers with mostly invented positions, retrying would
just ask the same broken question again — that should fail the task, not
loop.
"""
import anthropic
import httpx2
import pytest

from tests.ai.test_generate_critical_position_suggestions import _org_with_operations
from app.modules.ai import llm
from app.modules.ai.llm import LLMOutputError
from app.modules.ai.tasks import (
    GENERATE_SUGGESTIONS_TASK,
    _RETRYABLE_ANTHROPIC_ERRORS,
    generate_suggestions,
    run_generation,
)

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _raising_anthropic(monkeypatch, exc: Exception):
    """Replace AsyncAnthropic with a fake whose call raises ``exc`` immediately."""

    async def parse(**kwargs):
        raise exc

    class _Client:
        messages = type("Messages", (), {"parse": staticmethod(parse)})()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(llm, "AsyncAnthropic", lambda **kwargs: _Client())


# ---------------------------------------------------------- the policy itself

def test_only_transient_anthropic_errors_are_retried():
    """Connection/timeout, rate limit, and Anthropic's own 5xx — nothing else."""
    assert _RETRYABLE_ANTHROPIC_ERRORS == (
        anthropic.APIConnectionError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
    )


def test_a_malformed_request_to_anthropic_is_not_in_the_retryable_set():
    """BadRequestError/AuthenticationError/... would just fail the same way again."""
    assert not issubclass(anthropic.BadRequestError, _RETRYABLE_ANTHROPIC_ERRORS)
    assert not issubclass(anthropic.AuthenticationError, _RETRYABLE_ANTHROPIC_ERRORS)


def test_an_unusable_answer_is_not_in_the_retryable_set():
    """A refused/cut-off/mostly-invented answer means the prompt is broken, not the connection."""
    assert not issubclass(LLMOutputError, _RETRYABLE_ANTHROPIC_ERRORS)


def test_the_task_is_registered_with_backoff_and_a_retry_ceiling():
    """The task carries its retry config: the right name, set, ceiling, and backoff."""
    assert generate_suggestions.name == GENERATE_SUGGESTIONS_TASK
    assert generate_suggestions.autoretry_for == _RETRYABLE_ANTHROPIC_ERRORS
    assert generate_suggestions.max_retries == 3
    assert generate_suggestions.retry_backoff is True
    assert generate_suggestions.retry_jitter is True


# ------------------------------------------- what actually happens on each error

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        anthropic.APIConnectionError(message="connection dropped", request=_REQUEST),
        anthropic.RateLimitError(
            "rate limited",
            response=httpx2.Response(429, request=_REQUEST, json={}),
            body=None,
        ),
        anthropic.InternalServerError(
            "server error",
            response=httpx2.Response(500, request=_REQUEST, json={}),
            body=None,
        ),
    ],
)
async def test_a_transient_error_propagates_out_of_run_generation(
    client, db_session, monkeypatch, exc
):
    """Nothing here swallows it — it must reach the task body for Celery to retry."""
    org_id, _ = await _org_with_operations(client, db_session, "task_retry1@example.com")
    _raising_anthropic(monkeypatch, exc)

    with pytest.raises(type(exc)):
        async with db_session.begin_nested():
            await run_generation(db_session, org_id)


@pytest.mark.asyncio
async def test_a_bad_request_to_anthropic_also_propagates_uncaught(client, db_session, monkeypatch):
    """Not retryable, but still not silently swallowed — the task must still fail visibly."""
    org_id, _ = await _org_with_operations(client, db_session, "task_retry2@example.com")
    _raising_anthropic(
        monkeypatch,
        anthropic.BadRequestError(
            "bad request", response=httpx2.Response(400, request=_REQUEST, json={}), body=None
        ),
    )

    with pytest.raises(anthropic.BadRequestError):
        async with db_session.begin_nested():
            await run_generation(db_session, org_id)
