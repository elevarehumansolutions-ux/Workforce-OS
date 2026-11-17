"""A test fixture for the tests that are ABOUT overdue tasks.

Since 2026-11-17 the API refuses to create a task, or change a deadline, to a time that has
passed (to-do 67). The overdue tests need tasks that are already overdue, and they build them with
a deadline in 2020. This fixture switches that one check off for the test that asks for it, so
those tests keep testing the overdue rules and not the creation rule (which has its own tests in
``test_past_deadline_refused.py``). Import it into a test module with
``from tests.tasks.past_deadlines import allow_past_deadlines  # noqa: F401`` and add
``pytestmark = pytest.mark.usefixtures("allow_past_deadlines")``.
"""
import pytest

from app.modules.tasks.service import TaskService


@pytest.fixture
def allow_past_deadlines(monkeypatch):
    """Let this test create tasks whose deadline has already passed."""
    monkeypatch.setattr(TaskService, "_refuse_past_deadline", staticmethod(lambda due_at: None))
