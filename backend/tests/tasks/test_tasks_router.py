"""HTTP-level tests for /tasks, slice A: create, read, edit, complete.

Uses a small realistic company so the permission rules are exercised for
real (08_DECISIONS.md 2026-10-07):

- Adaeze: HR administrator (the org owner, no employee record)
- Dispatch department, headed by Tunde (membership role is plain ``employee``)
- Chidi and Bola: ordinary employees in Dispatch
- Dana: ``manager`` role, in Dispatch
- Sam: ``manager`` role, in Sales (a department with no head)
"""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.conftest import register_verified_and_login

TASKS = "/api/v1/tasks"
DEPARTMENTS = "/api/v1/departments"
POSITIONS = "/api/v1/positions"
EMPLOYEES = "/api/v1/employees"
MEMBERSHIPS = "/api/v1/memberships"
NOTIFICATIONS = "/api/v1/notifications"
AUDIT = "/api/v1/audit-log"
AUTH = "/api/v1/auth"
KPIS = "/api/v1/kpis"
DUE = "2026-12-01T10:00:00+00:00"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _member(client, monkeypatch, hr_h, email: str, role: str, position_id: str, first: str) -> SimpleNamespace:
    """Invite and accept a teammate, then give them an employee record linked to their login."""
    import app.modules.tenancy_identity.router as membership_router

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router, "dispatch_invite_email", mock_dispatch)
    await client.post(MEMBERSHIPS, json={"email": email, "role": role}, headers=hr_h)
    token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accepted = (await client.post(
        f"{AUTH}/accept-invite",
        json={"token": token, "full_name": f"{first} Tester", "password": "Password123#",
              "confirm_password": "Password123#"},
    )).json()
    employee = await client.post(
        EMPLOYEES,
        json={"position_id": position_id, "user_id": accepted["user"]["id"], "first_name": first,
              "last_name": "Tester", "work_email": email, "start_date": "2026-01-01"},
        headers=hr_h,
    )
    return SimpleNamespace(
        h=_auth_header(accepted["access_token"]),
        user_id=accepted["user"]["id"],
        employee_id=employee.json()["id"],
    )


async def _world(client, monkeypatch, tag: str) -> SimpleNamespace:
    """The company described in the module docstring."""
    owner = await register_verified_and_login(client, email=f"tk_hr_{tag}@example.com")
    hr = _auth_header(owner["access_token"])
    dispatch = (await client.post(DEPARTMENTS, json={"name": "Dispatch"}, headers=hr)).json()["id"]
    sales = (await client.post(DEPARTMENTS, json={"name": "Sales"}, headers=hr)).json()["id"]
    dispatch_pos = (await client.post(POSITIONS, json={"department_id": dispatch, "title": "Officer"}, headers=hr)).json()["id"]
    sales_pos = (await client.post(POSITIONS, json={"department_id": sales, "title": "Rep"}, headers=hr)).json()["id"]
    tunde = await _member(client, monkeypatch, hr, f"tk_tunde_{tag}@example.com", "employee", dispatch_pos, "Tunde")
    chidi = await _member(client, monkeypatch, hr, f"tk_chidi_{tag}@example.com", "employee", dispatch_pos, "Chidi")
    bola = await _member(client, monkeypatch, hr, f"tk_bola_{tag}@example.com", "employee", dispatch_pos, "Bola")
    dana = await _member(client, monkeypatch, hr, f"tk_dana_{tag}@example.com", "manager", dispatch_pos, "Dana")
    sam = await _member(client, monkeypatch, hr, f"tk_sam_{tag}@example.com", "manager", sales_pos, "Sam")
    await client.patch(f"{DEPARTMENTS}/{dispatch}", json={"head_employee_id": tunde.employee_id}, headers=hr)
    return SimpleNamespace(
        hr=hr, owner=owner, dispatch=dispatch, sales=sales,
        tunde=tunde, chidi=chidi, bola=bola, dana=dana, sam=sam,
    )


async def _task(client, h, department_id: str, title: str = "Deliver the shipment", **extra):
    return await client.post(TASKS, json={"department_id": department_id, "title": title, **extra}, headers=h)


async def _clock_in(client, *people) -> None:
    """Clock people in: an assignee only sees and works on their tasks while clocked in."""
    for person in people:
        assert (await client.post("/api/v1/attendance/clock-in", headers=person.h)).status_code == 200


def _ids(resp) -> list[str]:
    return [t["id"] for t in resp.json()["data"]]


@pytest.mark.asyncio
async def test_hr_creates_a_task_linked_to_a_kpi(client, monkeypatch):
    """The KPI link is stored, validated, and usable as a filter."""
    w = await _world(client, monkeypatch, "1")
    kpi = await client.post(
        KPIS, json={"department_id": w.dispatch, "name": "On-time deliveries", "weight": 100}, headers=w.hr
    )

    created = await _task(client, w.hr, w.dispatch, kpi_id=kpi.json()["id"],
                          assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)
    unknown = await _task(client, w.hr, w.dispatch, kpi_id=str(uuid.uuid4()))
    filtered = await client.get(TASKS, params={"kpi_id": kpi.json()["id"]}, headers=w.hr)

    assert created.status_code == 200
    body = created.json()
    assert body["kpi_id"] == kpi.json()["id"] and body["status"] == "open" and body["completed_at"] is None
    assert body["assigned_to_employee_id"] == w.chidi.employee_id
    assert body["created_by_user_id"] == w.owner["user"]["id"]
    assert unknown.status_code == 404 and unknown.json()["code"] == "KPI_NOT_FOUND"
    assert _ids(filtered) == [body["id"]]


@pytest.mark.asyncio
async def test_who_may_create_a_task(client, monkeypatch):
    """HR, the manager role and the department head can; a plain employee cannot."""
    w = await _world(client, monkeypatch, "2")

    by_employee = await _task(client, w.chidi.h, w.dispatch)
    by_head = await _task(client, w.tunde.h, w.dispatch)      # role "employee", but heads Dispatch
    by_manager = await _task(client, w.dana.h, w.dispatch)
    by_hr = await _task(client, w.hr, w.sales)

    assert by_employee.status_code == 403 and by_employee.json()["code"] == "PERMISSION_DENIED"
    assert by_head.status_code == by_manager.status_code == by_hr.status_code == 200


@pytest.mark.asyncio
async def test_a_manager_from_another_department_lands_the_task_on_the_head(client, monkeypatch):
    """Sam (Sales) asks Dispatch for something: it goes to Tunde, who is told."""
    w = await _world(client, monkeypatch, "3")

    resp = await _task(client, w.sam.h, w.dispatch, title="Rush order")

    assert resp.status_code == 200
    assert resp.json()["assigned_to_employee_id"] == w.tunde.employee_id
    assert resp.json()["created_by_user_id"] == w.sam.user_id
    titles = [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.tunde.h)).json()]
    assert "New task: Rush order" in titles


@pytest.mark.asyncio
async def test_an_outsider_cannot_pick_the_individual(client, monkeypatch):
    """Sam may not hand Dispatch's work to Chidi directly."""
    w = await _world(client, monkeypatch, "4")

    resp = await _task(client, w.sam.h, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)

    assert resp.status_code == 422
    assert "head" in resp.json()["message"]


@pytest.mark.asyncio
async def test_a_task_for_a_department_with_no_head_stays_unassigned_and_hr_is_told(client, monkeypatch):
    """Dana (Dispatch) asks Sales, which has no head: nobody to receive it."""
    w = await _world(client, monkeypatch, "5")

    resp = await _task(client, w.dana.h, w.sales, title="Quote for Acme")

    assert resp.status_code == 200 and resp.json()["assigned_to_employee_id"] is None
    titles = [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.hr)).json()]
    assert "A task for Sales has no one to receive it" in titles


@pytest.mark.asyncio
async def test_a_colleague_in_the_same_department_can_choose_the_assignee(client, monkeypatch):
    """Dana assigns Bola; Bola is told; an offboarded or unknown assignee is refused."""
    w = await _world(client, monkeypatch, "6")
    await client.post(f"{EMPLOYEES}/{w.chidi.employee_id}/offboard", headers=w.hr)

    ok = await _task(client, w.dana.h, w.dispatch, title="Check tyres", assigned_to_employee_id=w.bola.employee_id)
    offboarded = await _task(client, w.dana.h, w.dispatch, assigned_to_employee_id=w.chidi.employee_id)
    unknown = await _task(client, w.dana.h, w.dispatch, assigned_to_employee_id=str(uuid.uuid4()))

    assert ok.status_code == 200 and ok.json()["assigned_to_employee_id"] == w.bola.employee_id
    assert "New task: Check tyres" in [n["title"] for n in (await client.get(NOTIFICATIONS, headers=w.bola.h)).json()]
    assert offboarded.status_code == 422
    assert unknown.status_code == 404 and unknown.json()["code"] == "EMPLOYEE_NOT_FOUND"


@pytest.mark.asyncio
async def test_who_can_see_which_tasks(client, monkeypatch):
    """Assignee: own. Head and same-department manager: the department's. Other manager: only what they created. HR: all."""
    w = await _world(client, monkeypatch, "7")
    await _clock_in(client, w.chidi, w.bola)
    t_chidi = (await _task(client, w.hr, w.dispatch, "Chidi's", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    t_bola = (await _task(client, w.hr, w.dispatch, "Bola's", assigned_to_employee_id=w.bola.employee_id)).json()["id"]
    t_sam = (await _task(client, w.sam.h, w.dispatch, "Sam's request")).json()["id"]

    assert set(_ids(await client.get(TASKS, headers=w.chidi.h))) == {t_chidi}
    assert (await client.get(f"{TASKS}/{t_bola}", headers=w.chidi.h)).status_code == 404
    assert set(_ids(await client.get(TASKS, headers=w.tunde.h))) == {t_chidi, t_bola, t_sam}
    assert set(_ids(await client.get(TASKS, headers=w.dana.h))) == {t_chidi, t_bola, t_sam}
    assert set(_ids(await client.get(TASKS, headers=w.sam.h))) == {t_sam}           # only what he created
    assert (await client.get(f"{TASKS}/{t_chidi}", headers=w.sam.h)).status_code == 404
    assert set(_ids(await client.get(TASKS, headers=w.hr))) == {t_chidi, t_bola, t_sam}


@pytest.mark.asyncio
async def test_who_can_edit_a_task_and_what_cannot_be_edited(client, monkeypatch):
    """HR, the head and the creator can; the assignee cannot; status and the assignee are not editable here."""
    w = await _world(client, monkeypatch, "8")
    await _clock_in(client, w.chidi)
    tid = (await _task(client, w.hr, w.dispatch, assigned_to_employee_id=w.chidi.employee_id, due_at=DUE)).json()["id"]
    url = f"{TASKS}/{tid}"

    assignee = await client.patch(url, json={"title": "Mine now"}, headers=w.chidi.h)
    other_manager = await client.patch(url, json={"title": "Dana's"}, headers=w.dana.h)   # sees it, doesn't manage it
    head = await client.patch(url, json={"title": "Renamed by the head"}, headers=w.tunde.h)
    moved = await client.patch(url, json={"due_at": "2026-12-05T10:00:00+00:00"}, headers=w.hr)
    status_attempt = await client.patch(url, json={"status": "completed"}, headers=w.hr)
    assignee_attempt = await client.patch(url, json={"assigned_to_employee_id": w.bola.employee_id}, headers=w.hr)
    empty = await client.patch(url, json={}, headers=w.hr)
    naive = await client.patch(url, json={"due_at": "2026-12-05T10:00:00"}, headers=w.hr)
    null_title = await client.patch(url, json={"title": None}, headers=w.hr)

    assert assignee.status_code == other_manager.status_code == 403
    assert head.status_code == 200 and head.json()["title"] == "Renamed by the head"
    assert moved.status_code == 200 and moved.json()["due_at"].startswith("2026-12-05")
    for rejected in (status_attempt, assignee_attempt, empty, naive, null_title):
        assert rejected.status_code == 422
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": tid}, headers=w.hr)
    changes = [e["changes"] for e in audit.json()["data"] if e["action"] == "update"]
    assert any(c["old"].get("due_at", "").startswith("2026-12-01") and c["new"]["due_at"].startswith("2026-12-05")
               for c in changes)


@pytest.mark.asyncio
async def test_completing_a_task(client, monkeypatch):
    """The assignee, the head and HR can; others cannot; a second completion is a 409 and the first time stands."""
    w = await _world(client, monkeypatch, "9")
    await _clock_in(client, w.chidi)
    mine = (await _task(client, w.hr, w.dispatch, "Mine", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    theirs = (await _task(client, w.hr, w.dispatch, "Theirs", assigned_to_employee_id=w.bola.employee_id)).json()["id"]
    hrs = (await _task(client, w.hr, w.dispatch, "HR closes")).json()["id"]

    not_visible = await client.post(f"{TASKS}/{theirs}/complete", headers=w.chidi.h)   # Chidi can't even see Bola's
    visible_not_allowed = await client.post(f"{TASKS}/{mine}/complete", headers=w.dana.h)  # Dana sees it, isn't assignee/head/HR
    done = await client.post(f"{TASKS}/{mine}/complete", headers=w.chidi.h)
    again = await client.post(f"{TASKS}/{mine}/complete", headers=w.chidi.h)
    by_head = await client.post(f"{TASKS}/{theirs}/complete", headers=w.tunde.h)
    by_hr = await client.post(f"{TASKS}/{hrs}/complete", headers=w.hr)

    assert not_visible.status_code == 404
    assert visible_not_allowed.status_code == 403
    assert done.status_code == 200 and done.json()["status"] == "completed" and done.json()["completed_at"]
    assert again.status_code == 409 and again.json()["code"] == "TASK_NOT_OPEN"
    assert by_head.status_code == by_hr.status_code == 200
    edit_after = await client.patch(f"{TASKS}/{mine}", json={"title": "Too late"}, headers=w.hr)
    assert edit_after.status_code == 409
    audit = await client.get(AUDIT, params={"entity_type": "task", "entity_id": mine}, headers=w.hr)
    assert {"create", "complete"} <= {e["action"] for e in audit.json()["data"]}
    complete_entry = next(e for e in audit.json()["data"] if e["action"] == "complete")
    assert complete_entry["changes"]["old"]["status"] == "open"
    assert complete_entry["changes"]["new"]["status"] == "completed"


@pytest.mark.asyncio
async def test_bad_input_is_refused(client, monkeypatch):
    """Empty title, a deadline with no timezone, an unknown department."""
    w = await _world(client, monkeypatch, "10")

    blank = await _task(client, w.hr, w.dispatch, title="   ")
    naive = await _task(client, w.hr, w.dispatch, due_at="2026-12-01T10:00:00")
    no_dept = await _task(client, w.hr, str(uuid.uuid4()))

    assert blank.status_code == 422
    assert naive.status_code == 422
    assert no_dept.status_code == 404 and no_dept.json()["code"] == "DEPARTMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_another_organization_cannot_see_or_use_the_task(client, monkeypatch):
    """Row-level security: other orgs get 404s."""
    w = await _world(client, monkeypatch, "11")
    other = await register_verified_and_login(client, email="tk_other_11@example.com")
    other_h = _auth_header(other["access_token"])
    tid = (await _task(client, w.hr, w.dispatch)).json()["id"]

    seen = await client.get(f"{TASKS}/{tid}", headers=other_h)
    listed = await client.get(TASKS, headers=other_h)
    into_foreign_department = await _task(client, other_h, w.dispatch)

    assert seen.status_code == 404
    assert listed.json()["data"] == []
    assert into_foreign_department.status_code == 404


@pytest.mark.asyncio
async def test_filters_and_pagination(client, monkeypatch):
    """Filter by assignee, department and status; page through a list."""
    w = await _world(client, monkeypatch, "12")
    a = (await _task(client, w.hr, w.dispatch, "A", assigned_to_employee_id=w.chidi.employee_id)).json()["id"]
    b = (await _task(client, w.hr, w.dispatch, "B", assigned_to_employee_id=w.bola.employee_id)).json()["id"]
    c = (await _task(client, w.hr, w.sales, "C")).json()["id"]
    await client.post(f"{TASKS}/{a}/complete", headers=w.hr)

    by_assignee = await client.get(TASKS, params={"assigned_to_employee_id": w.bola.employee_id}, headers=w.hr)
    by_department = await client.get(TASKS, params={"department_id": w.sales}, headers=w.hr)
    completed = await client.get(TASKS, params={"status": "completed"}, headers=w.hr)
    page1 = await client.get(TASKS, params={"limit": 2}, headers=w.hr)
    page2 = await client.get(TASKS, params={"limit": 2, "page": 2}, headers=w.hr)

    assert _ids(by_assignee) == [b]
    assert _ids(by_department) == [c]
    assert _ids(completed) == [a]
    assert len(_ids(page1)) == 2 and page1.json()["pagination"]["total"] == 3
    assert page1.json()["pagination"]["has_next"] is True
    assert len(_ids(page2)) == 1
    assert set(_ids(page1)) | set(_ids(page2)) == {a, b, c}
