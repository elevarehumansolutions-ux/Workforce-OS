"""The email that goes with "a task landed on you", and the unread count behind the bell
(08_DECISIONS.md 2026-11-14).

Scenario: HR starts a case; the first step's task goes to its default person, or to the
department head, or to HR when there is no head. That person gets an in-app notification AND an
email, and the bell's number goes up. Nothing is emailed for work that was not saved.
"""
import pytest

from app.modules.audit_and_notification.task_email import dispatch_task_email
from tests.tasks.test_tasks_router import DUE, NOTIFICATIONS, TASKS, _task, _world
from tests.workflow.test_instance_start import _start, _template


def _capture_emails(monkeypatch) -> list:
    """Replace the queueing of the background email so a test can see what would be sent."""
    sent = []
    monkeypatch.setattr(
        dispatch_task_email, "delay", lambda email, title, body, link: sent.append((email, title, body, link))
    )
    return sent


@pytest.mark.asyncio
async def test_the_default_person_of_the_first_step_is_emailed(client, monkeypatch):
    w = await _world(client, monkeypatch, "te1")
    sent = _capture_emails(monkeypatch)
    template = await _template(
        client, w, ("Sales hand-off", w.sales, {"default_assignee_employee_id": w.dana.employee_id})
    )

    await _start(client, w.hr, template["id"])

    assert len(sent) == 1
    email, title, body, link = sent[0]
    assert email == "tk_dana_te1@example.com"
    assert title == "New task: Sales hand-off: Zenith Ltd"
    assert "assigned to you" in body
    assert "/tasks/" in link


@pytest.mark.asyncio
async def test_a_step_with_no_default_person_emails_the_department_head(client, monkeypatch):
    w = await _world(client, monkeypatch, "te2")
    sent = _capture_emails(monkeypatch)
    # Dispatch's head is Tunde.
    template = await _template(client, w, ("Dispatch the goods", w.dispatch, {}))

    await _start(client, w.hr, template["id"])

    assert [s[0] for s in sent] == ["tk_tunde_te2@example.com"]
    assert "needs an owner" in sent[0][1]


@pytest.mark.asyncio
async def test_a_department_with_no_head_emails_hr(client, monkeypatch):
    w = await _world(client, monkeypatch, "te3")
    sent = _capture_emails(monkeypatch)
    # Sales has no head.
    template = await _template(client, w, ("Close the deal", w.sales, {}))

    await _start(client, w.hr, template["id"])

    assert [s[0] for s in sent] == ["tk_hr_te3@example.com"]


@pytest.mark.asyncio
async def test_a_task_given_to_someone_by_a_person_is_emailed_to_them(client, monkeypatch):
    w = await _world(client, monkeypatch, "te4")
    sent = _capture_emails(monkeypatch)

    resp = await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)

    assert resp.status_code == 200
    assert [s[0] for s in sent] == ["tk_chidi_te4@example.com"]


@pytest.mark.asyncio
async def test_nobody_is_emailed_about_a_task_they_gave_themselves(client, monkeypatch):
    w = await _world(client, monkeypatch, "te5")
    sent = _capture_emails(monkeypatch)

    resp = await _task(client, w.dana.h, w.dispatch, assigned_to_employee_id=w.dana.employee_id, due_at=DUE)

    assert resp.status_code == 200
    assert sent == []


@pytest.mark.asyncio
async def test_reassigning_emails_the_new_owner_only(client, monkeypatch):
    w = await _world(client, monkeypatch, "te6")
    task = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)).json()
    sent = _capture_emails(monkeypatch)

    resp = await client.post(
        f"{TASKS}/{task['id']}/reassign",
        json={"assigned_to_employee_id": w.bola.employee_id, "due_at": DUE},
        headers=w.hr,
    )

    assert resp.status_code == 200
    # Bola is told it is theirs; Chidi (who lost it) gets the in-app notice but no email.
    assert [s[0] for s in sent] == ["tk_bola_te6@example.com"]


@pytest.mark.asyncio
async def test_the_bell_counts_unread_notifications_and_read_all_clears_it(client, monkeypatch):
    w = await _world(client, monkeypatch, "te7")
    _capture_emails(monkeypatch)
    count_url = f"{NOTIFICATIONS}/unread-count"
    assert (await client.get(count_url, headers=w.chidi.h)).json() == {"unread": 0}

    await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)
    await _task(client, w.hr, w.dispatch, title="Second one", assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)

    assert (await client.get(count_url, headers=w.chidi.h)).json() == {"unread": 2}
    # Someone else's notifications are not counted for Bola.
    assert (await client.get(count_url, headers=w.bola.h)).json() == {"unread": 0}

    await client.post(f"{NOTIFICATIONS}/read-all", headers=w.chidi.h)

    assert (await client.get(count_url, headers=w.chidi.h)).json() == {"unread": 0}


@pytest.mark.asyncio
async def test_the_unread_count_needs_a_signed_in_person(client):
    resp = await client.get(f"{NOTIFICATIONS}/unread-count")

    assert resp.status_code == 401
