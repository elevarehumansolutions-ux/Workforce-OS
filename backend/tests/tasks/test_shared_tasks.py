"""One task assigned to several departments at once (08_DECISIONS.md 2026-11-14, "Together steps", case 3).

Scenario: HR needs Dispatch and Sales to prepare a shipment. One request creates a task for each department; each
is completed on its own, they are linked by a shared group id, and each person is told and emailed.
"""
import pytest

from app.modules.audit_and_notification.task_email import dispatch_task_email
from tests.tasks.test_tasks_router import DUE, NOTIFICATIONS, TASKS, _world


async def _create_shared(client, headers, w, also_for, **extra):
    body = {"department_id": w.dispatch, "title": "Prepare the shipment", "due_at": DUE, "also_for": also_for, **extra}
    return await client.post(TASKS, json=body, headers=headers)


@pytest.mark.asyncio
async def test_one_request_creates_a_linked_task_per_department(client, monkeypatch):
    w = await _world(client, monkeypatch, "st1")

    resp = await _create_shared(
        client, w.hr, w,
        [{"department_id": w.sales, "assigned_to_employee_id": w.sam.employee_id}],
        assigned_to_employee_id=w.chidi.employee_id,
    )

    assert resp.status_code == 200, resp.text
    first = resp.json()
    group = first["shared_group_id"]
    assert group is not None and first["department_id"] == w.dispatch
    siblings = (await client.get(TASKS, params={"shared_group_id": group}, headers=w.hr)).json()["data"]
    assert sorted((t["department_id"], t["assigned_to_employee_id"]) for t in siblings) == sorted(
        [(w.dispatch, w.chidi.employee_id), (w.sales, w.sam.employee_id)]
    )
    assert {t["title"] for t in siblings} == {"Prepare the shipment"}
    assert {t["due_at"] for t in siblings} == {first["due_at"]}


@pytest.mark.asyncio
async def test_each_person_is_told_and_emailed(client, monkeypatch):
    w = await _world(client, monkeypatch, "st2")
    sent = []
    monkeypatch.setattr(dispatch_task_email, "delay", lambda email, title, body, link: sent.append(email))

    await _create_shared(
        client, w.hr, w,
        [{"department_id": w.sales, "assigned_to_employee_id": w.sam.employee_id}],
        assigned_to_employee_id=w.chidi.employee_id,
    )

    assert sorted(sent) == ["tk_chidi_st2@example.com", "tk_sam_st2@example.com"]
    assert "New task: Prepare the shipment" in [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.sam.h)).json()]


@pytest.mark.asyncio
async def test_each_task_is_completed_on_its_own(client, monkeypatch):
    w = await _world(client, monkeypatch, "st3")
    first = (await _create_shared(
        client, w.hr, w,
        [{"department_id": w.sales, "assigned_to_employee_id": w.sam.employee_id}],
        assigned_to_employee_id=w.chidi.employee_id,
    )).json()
    siblings = (await client.get(TASKS, params={"shared_group_id": first["shared_group_id"]}, headers=w.hr)).json()["data"]
    dispatch_task = next(t for t in siblings if t["department_id"] == w.dispatch)

    assert (await client.post(f"{TASKS}/{dispatch_task['id']}/complete", headers=w.hr)).status_code == 200

    after = (await client.get(TASKS, params={"shared_group_id": first["shared_group_id"]}, headers=w.hr)).json()["data"]
    assert sorted(t["status"] for t in after) == ["completed", "open"]


@pytest.mark.asyncio
async def test_a_head_sees_only_his_own_departments_copy(client, monkeypatch):
    w = await _world(client, monkeypatch, "st4")
    first = (await _create_shared(
        client, w.hr, w, [{"department_id": w.sales}], assigned_to_employee_id=w.chidi.employee_id
    )).json()

    seen_by_tunde = (await client.get(TASKS, params={"shared_group_id": first["shared_group_id"]}, headers=w.tunde.h)).json()["data"]

    assert [t["department_id"] for t in seen_by_tunde] == [w.dispatch]  # Tunde heads Dispatch, not Sales


@pytest.mark.asyncio
async def test_the_same_department_and_person_twice_is_refused_and_nothing_is_saved(client, monkeypatch):
    w = await _world(client, monkeypatch, "st5")

    resp = await _create_shared(
        client, w.hr, w, [{"department_id": w.sales}, {"department_id": w.sales}]
    )

    assert resp.status_code == 422 and "listed twice" in resp.json()["message"]
    assert (await client.get(TASKS, params={"limit": 100}, headers=w.hr)).json()["data"] == []


@pytest.mark.asyncio
async def test_a_refusal_for_one_department_saves_none_of_them(client, db_session, monkeypatch):
    """Sam is a Sales manager: he may create for Sales, but naming a person in Dispatch (another department) is refused."""
    w = await _world(client, monkeypatch, "st6")
    body = {
        "department_id": w.sales, "title": "Joint prep", "due_at": DUE,
        "also_for": [{"department_id": w.dispatch, "assigned_to_employee_id": w.chidi.employee_id}],
    }

    commits = []
    original_commit = db_session.commit

    async def spy_commit():
        commits.append(1)
        await original_commit()

    monkeypatch.setattr(db_session, "commit", spy_commit)

    resp = await client.post(TASKS, json=body, headers=w.sam.h)

    assert resp.status_code == 422  # an outsider may not name the person in another department
    # The Sales task was created before the Dispatch one was refused. Nothing is saved because the router never
    # reaches its single commit, and in production a failed request's session is rolled back (get_db). The shared
    # test session cannot show that rollback, so the proof here is that no commit happened.
    assert commits == []


@pytest.mark.asyncio
async def test_an_ordinary_employee_may_not_create_shared_tasks(client, monkeypatch):
    w = await _world(client, monkeypatch, "st7")

    resp = await _create_shared(client, w.chidi.h, w, [{"department_id": w.sales}])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_a_task_without_also_for_is_unchanged(client, monkeypatch):
    w = await _world(client, monkeypatch, "st8")

    resp = await client.post(
        TASKS, json={"department_id": w.dispatch, "title": "Solo", "due_at": DUE}, headers=w.hr
    )

    assert resp.status_code == 200 and resp.json()["shared_group_id"] is None


@pytest.mark.asyncio
async def test_more_than_five_extra_departments_is_refused(client, monkeypatch):
    w = await _world(client, monkeypatch, "st9")

    resp = await _create_shared(client, w.hr, w, [{"department_id": w.sales}] * 6)

    assert resp.status_code == 422
