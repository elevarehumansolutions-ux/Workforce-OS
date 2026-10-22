"""Tests for who may see whose performance numbers (M12 slice E).

Uses the Task module's small company: Adaeze (HR, no employee record), Tunde
(heads Dispatch), Chidi and Bola (ordinary, Dispatch), Dana (``manager``,
Dispatch) and Sam (``manager``, Sales).
"""
import uuid

import pytest
from sqlalchemy import select

from app.modules.scoring.access import load_performance_scope
from app.modules.tenancy_identity.models import Membership
from tests.conftest import set_org_context
from tests.tasks.test_tasks_router import _member, _world


async def _scope_of(db_session, w, user_id: str):
    """The performance scope of the person with this login, in the test company."""
    await set_org_context(db_session, w.owner["organization"]["id"])
    result = await db_session.execute(select(Membership).where(Membership.user_id == uuid.UUID(user_id)))
    return await load_performance_scope(db_session, result.scalar_one())


@pytest.mark.asyncio
async def test_hr_and_executives_see_everyone(client, monkeypatch, db_session):
    """HR and business executives see every department and person."""
    w = await _world(client, monkeypatch, "acc1")
    executive = await _member(client, monkeypatch, w.hr, "tk_exec_acc1@example.com", "business_executive",
                              (await client.get("/api/v1/positions", headers=w.hr)).json()["data"][0]["id"], "Eve")

    hr_scope = await _scope_of(db_session, w, w.owner["user"]["id"])
    exec_scope = await _scope_of(db_session, w, executive.user_id)

    assert hr_scope.sees_all is True
    assert hr_scope.employee_id is None  # Adaeze has no employee record
    assert exec_scope.sees_all is True
    assert hr_scope.can_see_department(uuid.UUID(w.sales)) is True
    assert exec_scope.can_see_person(uuid.UUID(w.chidi.employee_id), uuid.UUID(w.dispatch)) is True


@pytest.mark.asyncio
async def test_a_head_and_a_manager_see_only_their_own_department(client, monkeypatch, db_session):
    """A head sees the department they head, a manager the one they work in, nobody else's."""
    w = await _world(client, monkeypatch, "acc2")
    dispatch, sales = uuid.UUID(w.dispatch), uuid.UUID(w.sales)
    chidi, sam = uuid.UUID(w.chidi.employee_id), uuid.UUID(w.sam.employee_id)

    tunde_scope = await _scope_of(db_session, w, w.tunde.user_id)  # heads Dispatch, role "employee"
    dana_scope = await _scope_of(db_session, w, w.dana.user_id)  # manager, works in Dispatch
    sam_scope = await _scope_of(db_session, w, w.sam.user_id)  # manager, works in Sales

    assert tunde_scope.can_see_person(chidi, dispatch) is True
    assert tunde_scope.can_see_person(sam, sales) is False
    assert tunde_scope.can_see_department(sales) is False
    assert dana_scope.can_see_person(chidi, dispatch) is True
    assert dana_scope.can_see_person(sam, sales) is False
    assert sam_scope.can_see_person(sam, sales) is True
    assert sam_scope.can_see_person(chidi, dispatch) is False
    assert sam_scope.can_see_department(dispatch) is False


@pytest.mark.asyncio
async def test_an_ordinary_employee_sees_only_themselves_and_gets_no_ranked_list(client, monkeypatch, db_session):
    """A colleague in the same department is not visible, and only HR, executives, heads and managers rank."""
    w = await _world(client, monkeypatch, "acc3")
    dispatch = uuid.UUID(w.dispatch)
    chidi, bola = uuid.UUID(w.chidi.employee_id), uuid.UUID(w.bola.employee_id)

    chidi_scope = await _scope_of(db_session, w, w.chidi.user_id)

    # Bola sits in the same department, but a colleague is not a head: no peeking.
    assert chidi_scope.can_see_person(chidi, dispatch) is True
    assert chidi_scope.can_see_person(bola, dispatch) is False
    assert chidi_scope.can_see_department(dispatch) is False
    assert chidi_scope.can_see_ranked_list() is False

    for ranked_list_viewer in (w.owner["user"]["id"], w.tunde.user_id, w.dana.user_id, w.sam.user_id):
        scope = await _scope_of(db_session, w, ranked_list_viewer)
        assert scope.can_see_ranked_list() is True
