"""The reminder before a deadline (08_DECISIONS.md 2026-11-15, "Reminder before the deadline").

Scenario: Chidi has a task. When a quarter of its time is left (never sooner than 1 hour, never earlier than 1 day before
the deadline) he is reminded once, in the app and by email, and asked whether something is holding it up, so a block can
be recorded BEFORE the deadline. Only he is reminded (not his head). A task too short to have a reminder still gets the
old "was something holding it up?" question after the deadline; a reminded task does not get it twice.
"""
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.modules.audit_and_notification.task_email import dispatch_task_email
from app.modules.tasks import tasks as task_jobs
from app.modules.tasks.models import Task
from app.modules.tasks.overdue import REMINDER_MAX_LEAD, REMINDER_MIN_LEAD, due_soon_clause, is_due_soon, reminder_lead
from app.modules.tasks.repository import TaskRepository
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import NOTIFICATIONS, _task, _world

NOW = datetime(2030, 6, 3, 10, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _titles_starting(notifications, prefix: str) -> list[str]:
    return [n["title"] for n in notifications if n["title"].startswith(prefix)]


async def _notifications(client, headers) -> list[dict]:
    return (await client.get(NOTIFICATIONS, headers=headers)).json()


async def _make_task(client, db_session, w, title: str, created: datetime, due: datetime, **extra) -> str:
    """A task for Chidi with a chosen creation time and deadline."""
    resp = await _task(
        client, w.hr, w.dispatch, title, assigned_to_employee_id=w.chidi.employee_id, due_at=due.isoformat(), **extra
    )
    task_id = resp.json()["id"]
    await set_org_context(db_session, w.owner["organization"]["id"])
    await db_session.execute(
        text("UPDATE tasks SET created_at = :created WHERE id = :id"), {"created": created, "id": task_id}
    )
    return task_id


async def _scan_at(db_session, w, now: datetime) -> int:
    """Run the per-organization scan job the way Celery would, as if it were ``now``."""
    org_id = w.owner["organization"]["id"]
    await set_org_context(db_session, org_id)
    return await task_jobs.run_announce_for_organization(db_session, uuid.UUID(org_id), now)


# ---- the rule: lead time, in Python


@pytest.mark.parametrize(
    "life, expected",
    [
        (timedelta(days=2), timedelta(hours=12)),  # a quarter of the time
        (timedelta(hours=3), HOUR),  # a quarter would be 45 minutes, so the floor of 1 hour applies
        (timedelta(days=10), timedelta(days=1)),  # a quarter would be 2.5 days, so the cap of 1 day applies
        (timedelta(hours=4), HOUR),
    ],
)
def test_the_lead_time_is_a_quarter_of_the_life_between_one_hour_and_one_day(life, expected):
    assert reminder_lead(life) == expected
    assert REMINDER_MIN_LEAD <= reminder_lead(life) <= REMINDER_MAX_LEAD


# ---- the rule: Python and SQL agree, case by case

# (name, hours the task has already lived, hours left, extra task fields, expected)
CASES = [
    ("a quarter of two days left", 36, 12, {}, True),
    ("a little earlier than that", 35, 13, {}, False),
    ("a long task, one day left", 9 * 24, 24, {}, True),
    ("a long task, more than a day left", 9 * 24, 25, {}, False),
    ("a three hour task, the last hour", 2, 1, {}, True),
    ("a short task has no reminder", 0.67, 0.17, {}, False),
    ("already past the deadline", 5, -1, {}, False),
    ("blocked right now", 36, 12, {"blocked_since": NOW}, False),
    ("nobody assigned", 36, 12, {"assigned_to_employee_id": None}, False),
    ("already reminded", 36, 12, {"due_soon_notified_at": NOW}, False),
    ("completed", 36, 12, {"status": "completed"}, False),
    ("approved blocked time moves the real deadline", 36, 11, {"approved_blocked_seconds": 3600}, True),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name, lived_hours, left_hours, extra, expected", CASES, ids=[c[0] for c in CASES])
async def test_python_and_sql_give_the_same_answer(client, db_session, monkeypatch, name, lived_hours, left_hours, extra, expected):
    w = await _world(client, monkeypatch, "ds" + str(abs(hash(name)) % 100000))
    created = NOW - timedelta(hours=lived_hours)
    # `due_at` is the written deadline; approved blocked seconds (if any) are added on top of it.
    approved = extra.get("approved_blocked_seconds", 0)
    due = NOW + timedelta(hours=left_hours) - timedelta(seconds=approved)
    task_id = await _make_task(client, db_session, w, "Rule case", created, due)
    fields = {k: v for k, v in extra.items() if k != "status"}
    sets = ", ".join(f"{k} = :{k}" for k in fields) or "title = title"
    status_sql = ", status = 'completed', completed_at = :now" if extra.get("status") == "completed" else ""
    await db_session.execute(
        text(f"UPDATE tasks SET {sets}{status_sql} WHERE id = :id"), {**fields, "id": task_id, "now": NOW}
    )

    task = await TaskRepository(db_session).get_task_by_id(uuid.UUID(task_id))
    await db_session.refresh(task)
    sql_says = (
        await db_session.execute(select(func.count()).select_from(Task).where(Task.id == task.id, due_soon_clause(NOW)))
    ).scalar_one() == 1

    assert is_due_soon(task, NOW) is expected
    assert sql_says is expected


# ---- the scan: who is told, how, and once


@pytest.mark.asyncio
async def test_the_assignee_is_reminded_in_the_app_and_by_email_and_nobody_else(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr1")
    sent = []
    monkeypatch.setattr(dispatch_task_email, "delay", lambda email, title, body, link: sent.append((email, title, body)))
    await _make_task(client, db_session, w, "Fix route", NOW - timedelta(hours=36), NOW + timedelta(hours=12))
    sent.clear()  # the email for being given the task is not under test here

    await _scan_at(db_session, w, NOW)

    chidi = _titles_starting(await _notifications(client, w.chidi.h), "Due soon")
    assert chidi == ["Due soon: Fix route"]
    body = next(n["body"] for n in await _notifications(client, w.chidi.h) if n["title"] == "Due soon: Fix route")
    assert "holding it up" in body and "mark it blocked now" in body and "Africa/Lagos" in body
    assert _titles_starting(await _notifications(client, w.tunde.h), "Due soon") == []  # the head is not reminded
    assert _titles_starting(await _notifications(client, w.hr), "Due soon") == []
    assert [(e, t) for e, t, _ in sent] == [("tk_chidi_dr1@example.com", "Due soon: Fix route")]


@pytest.mark.asyncio
async def test_each_task_is_reminded_only_once(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr2")
    monkeypatch.setattr(dispatch_task_email, "delay", lambda *args: None)
    await _make_task(client, db_session, w, "Fix route", NOW - timedelta(hours=36), NOW + timedelta(hours=12))

    first = await _scan_at(db_session, w, NOW)
    again = await _scan_at(db_session, w, NOW + timedelta(minutes=10))

    assert len(_titles_starting(await _notifications(client, w.chidi.h), "Due soon")) == 1
    assert first == 0 and again == 0  # the scan returns the OVERDUE count; nothing is overdue yet


@pytest.mark.asyncio
async def test_a_task_not_yet_in_its_window_is_left_alone(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr3")
    monkeypatch.setattr(dispatch_task_email, "delay", lambda *args: None)
    await _make_task(client, db_session, w, "Plenty of time", NOW - timedelta(hours=36), NOW + timedelta(hours=40))

    await _scan_at(db_session, w, NOW)

    assert _titles_starting(await _notifications(client, w.chidi.h), "Due soon") == []


@pytest.mark.asyncio
async def test_a_reminded_task_does_not_get_the_holding_up_question_again_after_the_deadline(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr4")
    monkeypatch.setattr(dispatch_task_email, "delay", lambda *args: None)
    await _make_task(client, db_session, w, "Fix route", NOW - timedelta(hours=36), NOW + timedelta(hours=12))
    await _scan_at(db_session, w, NOW)  # the reminder, with the question

    await _scan_at(db_session, w, NOW + timedelta(hours=13))  # the deadline has passed

    titles = [n["title"] for n in await _notifications(client, w.chidi.h)]
    assert "Task overdue: Fix route" in titles  # the overdue alert still goes out
    assert not any(t.startswith("Was something holding up") for t in titles)  # the question was already asked


@pytest.mark.asyncio
async def test_a_task_too_short_for_a_reminder_still_gets_the_old_question_when_overdue(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr5")
    monkeypatch.setattr(dispatch_task_email, "delay", lambda *args: None)
    await _make_task(client, db_session, w, "Quick one", NOW - timedelta(minutes=40), NOW + timedelta(minutes=10))
    await _scan_at(db_session, w, NOW)  # inside the final hour, but the whole task lived less than an hour

    assert _titles_starting(await _notifications(client, w.chidi.h), "Due soon") == []

    await _scan_at(db_session, w, NOW + timedelta(minutes=30))

    assert _titles_starting(await _notifications(client, w.chidi.h), "Was something holding up") == [
        "Was something holding up: Quick one?"
    ]


@pytest.mark.asyncio
async def test_a_new_deadline_gets_its_own_reminder(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr6")
    monkeypatch.setattr(dispatch_task_email, "delay", lambda *args: None)
    task_id = await _make_task(client, db_session, w, "Fix route", NOW - timedelta(hours=36), NOW + timedelta(hours=12))
    await _scan_at(db_session, w, NOW)
    repo = TaskRepository(db_session)
    task = await repo.get_task_by_id(uuid.UUID(task_id))
    assert task.due_soon_notified_at is not None

    await repo.update_task(task, {"due_at": NOW + timedelta(days=3)})

    task = await repo.get_task_by_id(uuid.UUID(task_id))
    assert task.due_soon_notified_at is None and task.overdue_notified_at is None


# ---- the lookup that tells the scan which organizations to visit (uses the database's own clock)


@pytest.mark.asyncio
async def test_the_scans_lookup_finds_an_organization_with_a_task_in_its_window(client, db_session, monkeypatch):
    w = await _world(client, monkeypatch, "dr7")
    org_id = uuid.UUID(w.owner["organization"]["id"])
    real_now = datetime.now(UTC)
    # Lived 3.5 hours, 30 minutes left: inside the final hour.
    task_id = await _make_task(
        client, db_session, w, "In the window", real_now - timedelta(hours=3), real_now + timedelta(minutes=30)
    )

    found = await TaskRepository(db_session).list_organizations_needing_scan()
    assert org_id in found

    # Plenty of time left: the organization no longer needs a visit for this task.
    await db_session.execute(
        text("UPDATE tasks SET due_at = :due WHERE id = :id"), {"due": real_now + timedelta(hours=2), "id": task_id}
    )
    found = await TaskRepository(db_session).list_organizations_needing_scan()
    assert org_id not in found


@pytest.mark.asyncio
async def test_the_reminder_email_footer_is_neutral(client, monkeypatch):
    """The email says the task needs your attention (it is used for reminders as well as new tasks)."""
    from app.core.email import ResendEmailService

    sent = {}

    async def fake_send(subject, recipients, html_body):
        sent["html"] = html_body

    service = object.__new__(ResendEmailService)
    service._send_html = fake_send
    await service.send_task_email("a@example.com", "Due soon: X", "Is something holding it up?", "https://x/tasks/1")

    assert "needs your attention" in sent["html"]
