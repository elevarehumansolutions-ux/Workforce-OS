"""The Celery worker must be told which modules hold tasks.

Scenario: a user signs up and the API queues "send verification email". The
worker only runs tasks it knows about — it learns them from ``include``.
An empty list (or an empty name in it) meant every queued task was rejected
as unregistered, or the worker refused to start.
"""
import importlib

from app.core.celery_app import celery

EXPECTED_TASK_MODULES = {
    "app.modules.auth.tasks",
    "app.modules.tenancy_identity.tasks",
}


def test_the_worker_is_told_about_every_task_module():
    """Each module that defines tasks is listed in ``include``."""
    assert EXPECTED_TASK_MODULES <= set(celery.conf.include)


def test_every_included_module_is_a_real_importable_module():
    """A blank or misspelled entry would stop the worker from starting."""
    for module_name in celery.conf.include:
        assert module_name, "empty module name in Celery include"
        importlib.import_module(module_name)


def test_the_email_tasks_are_registered_once_their_modules_load():
    """Importing the included modules registers the tasks under their full names."""
    for module_name in celery.conf.include:
        importlib.import_module(module_name)

    assert {
        "app.modules.auth.tasks.dispatch_verification_email",
        "app.modules.auth.tasks.dispatch_password_reset_email",
        "app.modules.tenancy_identity.tasks.dispatch_invite_email",
    } <= set(celery.tasks)
