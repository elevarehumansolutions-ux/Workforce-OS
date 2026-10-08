"""Names of Celery tasks triggered across module boundaries.

A module that needs another module's background job to run does so by
**name** (``celery.send_task(name, args=...)``), never by importing that
module's task function directly — an import would violate this project's
dependency direction (e.g. Org Structure sits underneath AI Suggestions and
must not import it; see 08_DECISIONS.md 2026-09-25/27).

The name is kept here, in one place, rather than as a literal string typed
again at each call site. A rename is still a real risk (it's a string
contract, not a Python reference the tools can follow), which is why the
owning module's test suite asserts the name it registers under matches this
constant exactly (see ``tests/ai/test_generation_task_retry.py``).
"""

AI_GENERATE_SUGGESTIONS_TASK = "app.modules.ai.tasks.generate_suggestions"
