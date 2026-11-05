"""HTTP-level tests for the leaderboard (M12 slice E part 3).

Uses the same Dispatch Q3 as the department summary tests: Bola 100 on one task,
Chidi 66.67 on six, Dana and Tunde with no tasks.
"""
import uuid

import pytest

from tests.scoring.test_department_performance import Q3, _dispatch_quarter
from tests.scoring.test_employee_scores import _compute_q3, _done, _task, at
from tests.tasks.test_tasks_router import _world

BOARD = "/api/v1/employees/leaderboard"


@pytest.mark.asyncio
async def test_hr_sees_everyone_with_a_score_ranked_with_their_context(client, monkeypatch, db_session):
    """Bola first on one task, Chidi second on six; people with no data are not listed."""
    w = await _world(client, monkeypatch, "lb1")
    await _dispatch_quarter(client, db_session, w)

    resp = await client.get(BOARD, params=Q3, headers=w.hr)

    assert resp.status_code == 200
    board = resp.json()
    assert (board["period_start"], board["period_end"]) == ("2026-07-01", "2026-09-30")
    rows = [
        (e["rank"], e["employee_name"], e["overall_score"], e["valid_tasks"], e["kpis_counted"], e["kpis_expected"])
        for e in board["entries"]
    ]
    assert rows == [(1, "Bola Tester", "100.00", 1, 1, 2), (2, "Chidi Tester", "66.67", 6, 1, 2)]
    assert board["entries"][0]["department_name"] == "Dispatch"
    assert board["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_equal_scores_share_a_rank_and_the_next_rank_skips(client, monkeypatch, db_session):
    """Dana also scores 100: Bola and Dana are both 1st, Chidi is 3rd (not 2nd)."""
    w = await _world(client, monkeypatch, "lb2")
    _, paperwork = await _dispatch_quarter(client, db_session, w)
    db_session.add(_task(w, "Dana's paperwork", paperwork, w.dana.employee_id, **_done(at(7, 12), at(7, 11))))
    await db_session.flush()
    await _compute_q3(db_session, w)

    board = (await client.get(BOARD, params=Q3, headers=w.hr)).json()

    assert [(e["rank"], e["employee_name"]) for e in board["entries"]] == [
        (1, "Bola Tester"), (1, "Dana Tester"), (3, "Chidi Tester"),
    ]


@pytest.mark.asyncio
async def test_who_may_open_the_leaderboard(client, monkeypatch, db_session):
    """An employee gets 404; a head or manager sees only their own departments; the department filter obeys the same rule."""
    w = await _world(client, monkeypatch, "lb3")
    await _dispatch_quarter(client, db_session, w)

    assert (await client.get(BOARD, params=Q3, headers=w.chidi.h)).status_code == 404

    for head_or_manager in (w.tunde.h, w.dana.h):
        board = (await client.get(BOARD, params=Q3, headers=head_or_manager)).json()
        assert [e["employee_name"] for e in board["entries"]] == ["Bola Tester", "Chidi Tester"]

    # Sam manages Sales: his board is Sales only (nobody there has a score), and Dispatch is not his to ask for.
    sam_board = await client.get(BOARD, params=Q3, headers=w.sam.h)
    assert sam_board.status_code == 200 and sam_board.json()["entries"] == []
    assert (await client.get(BOARD, params={**Q3, "department_id": w.dispatch}, headers=w.sam.h)).status_code == 404

    only_sales = await client.get(BOARD, params={**Q3, "department_id": w.sales}, headers=w.hr)
    assert only_sales.status_code == 200 and only_sales.json()["entries"] == []
    assert (await client.get(BOARD, params={**Q3, "department_id": str(uuid.uuid4())}, headers=w.hr)).status_code == 404


@pytest.mark.asyncio
async def test_the_leaderboard_is_paged_and_keeps_ranks_across_pages(client, monkeypatch, db_session):
    """One per page: page 2 is Chidi, still rank 2."""
    w = await _world(client, monkeypatch, "lb4")
    await _dispatch_quarter(client, db_session, w)

    second = (await client.get(BOARD, params={**Q3, "page": 2, "limit": 1}, headers=w.hr)).json()

    assert [(e["rank"], e["employee_name"]) for e in second["entries"]] == [(2, "Chidi Tester")]
    assert second["pagination"] == {
        "page": 2, "limit": 1, "total": 2, "total_pages": 2, "has_next": False, "has_previous": True,
    }
