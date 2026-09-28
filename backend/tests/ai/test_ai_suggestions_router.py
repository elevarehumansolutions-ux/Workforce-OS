"""HTTP-level tests for the AI suggestions endpoints.

Scenario: HR admin Adaeze reviews AI suggestions for her organization. Real
requests, real tokens — including the role gates and tenant isolation.
"""
import uuid

import pytest

from tests.conftest import register_verified_and_login, set_org_context
from tests.audit_and_notification.test_audit_log import _invite_and_accept
from app.modules.ai.schemas import AISuggestionCreateRequest
from app.modules.ai.service import AISuggestionService

SUGGESTIONS = "/api/v1/ai-suggestions"
POSITIONS = "/api/v1/positions"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _org_with_suggestions(client, db_session, email):
    """Register an org (its founder is an HR admin) with two pending suggestions.

    One critical_position for a General Manager, one missing_department "Legal".
    """
    owner = await register_verified_and_login(client, email=email)
    h = _auth_header(owner["access_token"])
    org_id = uuid.UUID(owner["organization"]["id"])
    dept = await client.post("/api/v1/departments", json={"name": "Ops"}, headers=h)
    pos = await client.post(
        POSITIONS, json={"department_id": dept.json()["id"], "title": "General Manager"}, headers=h
    )
    await set_org_context(db_session, org_id)
    service = AISuggestionService(db_session)
    position_suggestion = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="critical_position",
            position_id=uuid.UUID(pos.json()["id"]),
            suggested_criticality_type="revenue_generating",
            suggested_risk_level="high",
            rationale="Owns delivery targets.",
        ),
    )
    department_suggestion = await service.create_suggestion_if_eligible(
        org_id,
        AISuggestionCreateRequest(
            suggestion_type="missing_department",
            suggested_department_name="Legal",
            rationale="No department owns contracts.",
        ),
    )
    return owner, h, pos.json()["id"], position_suggestion.id, department_suggestion.id


# ---------------------------------------------------------------- reject

@pytest.mark.asyncio
async def test_adaeze_rejects_a_suggestion(client, db_session):
    """Reject returns the suggestion as rejected; doing it again is a 409; an unknown id a 404."""
    _, h, _, suggestion_id, _ = await _org_with_suggestions(client, db_session, "ai_rt_rej@example.com")

    resp = await client.post(f"{SUGGESTIONS}/{suggestion_id}/reject", headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["reviewed_at"] is not None

    assert (await client.post(f"{SUGGESTIONS}/{suggestion_id}/reject", headers=h)).status_code == 409
    assert (await client.post(f"{SUGGESTIONS}/{uuid.uuid4()}/reject", headers=h)).status_code == 404


# ---------------------------------------------------------------- approve

@pytest.mark.asyncio
async def test_adaeze_approves_and_the_position_becomes_critical(client, db_session):
    """Approve applies the AI's values to the real position."""
    _, h, position_id, suggestion_id, _ = await _org_with_suggestions(
        client, db_session, "ai_rt_appr@example.com"
    )

    resp = await client.post(f"{SUGGESTIONS}/{suggestion_id}/approve", headers=h)

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    position = (await client.get(f"{POSITIONS}/{position_id}", headers=h)).json()
    assert (position["is_critical"], position["criticality_type"], position["risk_level"]) == (
        True,
        "revenue_generating",
        "high",
    )


@pytest.mark.asyncio
async def test_approving_a_department_whose_name_now_exists_is_a_409(client, db_session):
    """A failed apply surfaces as a 409 through the real router.

    That the suggestion then stays pending is proven at the service level
    (test_approve_missing_department_fails_if_the_name_now_exists, with a
    SAVEPOINT standing in for the request rollback): the test client shares
    one long-lived session across requests, so it can't observe the rollback
    that production's per-request session performs when the router never
    reaches its commit.
    """
    _, h, _, _, department_suggestion_id = await _org_with_suggestions(
        client, db_session, "ai_rt_apprfail@example.com"
    )
    await client.post("/api/v1/departments", json={"name": "legal"}, headers=h)

    resp = await client.post(f"{SUGGESTIONS}/{department_suggestion_id}/approve", headers=h)

    assert resp.status_code == 409


# ---------------------------------------------------------------- edit

@pytest.mark.asyncio
async def test_adaeze_edits_only_the_risk_level(client, db_session):
    """Edit sends only what changed; the rest keeps the AI's value, and it's applied."""
    _, h, position_id, suggestion_id, _ = await _org_with_suggestions(
        client, db_session, "ai_rt_edit@example.com"
    )

    resp = await client.post(f"{SUGGESTIONS}/{suggestion_id}/edit", json={"risk_level": "medium"}, headers=h)

    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["reviewed_risk_level"], body["reviewed_criticality_type"]) == (
        "edited",
        "medium",
        "revenue_generating",
    )
    position = (await client.get(f"{POSITIONS}/{position_id}", headers=h)).json()
    assert position["risk_level"] == "medium"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},  # nothing to change
        {"revenue_allocation_percentage": "30"},  # doesn't fit a position suggestion
        {"risk_level": "high"},  # identical to the AI's — that's an approve
        {"risk_level": "extremely spicy"},  # not a real risk level
    ],
)
async def test_edit_refuses_nonsense_with_a_422(client, db_session, body):
    """Empty, ill-fitting, no-change, and invalid edits are all 422 — and change nothing."""
    _, h, _, suggestion_id, _ = await _org_with_suggestions(client, db_session, f"ai_rt_e422_{uuid.uuid4().hex[:8]}@example.com")

    resp = await client.post(f"{SUGGESTIONS}/{suggestion_id}/edit", json=body, headers=h)

    assert resp.status_code == 422
    still = await client.get(f"{SUGGESTIONS}?status=pending&suggestion_type=critical_position", headers=h)
    assert len(still.json()["data"]) == 1


# ---------------------------------------------------------------- list

@pytest.mark.asyncio
async def test_list_filters_by_status_and_type_and_paginates(client, db_session):
    """The queue can be filtered and paged; a bad filter value is a 422."""
    _, h, _, suggestion_id, _ = await _org_with_suggestions(client, db_session, "ai_rt_list@example.com")
    await client.post(f"{SUGGESTIONS}/{suggestion_id}/reject", headers=h)

    everything = await client.get(SUGGESTIONS, headers=h)
    assert everything.status_code == 200
    assert everything.json()["pagination"]["total"] == 2

    rejected = await client.get(f"{SUGGESTIONS}?status=rejected", headers=h)
    assert [row["id"] for row in rejected.json()["data"]] == [str(suggestion_id)]

    depts = await client.get(f"{SUGGESTIONS}?suggestion_type=missing_department", headers=h)
    assert [row["suggestion_type"] for row in depts.json()["data"]] == ["missing_department"]

    page_one = await client.get(f"{SUGGESTIONS}?limit=1&page=1", headers=h)
    assert len(page_one.json()["data"]) == 1
    assert page_one.json()["pagination"]["total_pages"] == 2

    assert (await client.get(f"{SUGGESTIONS}?status=bogus", headers=h)).status_code == 422


# ---------------------------------------------------------------- access

@pytest.mark.asyncio
async def test_requests_without_a_token_are_401(client, db_session):
    """Every endpoint requires authentication."""
    assert (await client.get(SUGGESTIONS)).status_code == 401
    assert (await client.post(f"{SUGGESTIONS}/{uuid.uuid4()}/reject")).status_code == 401


@pytest.mark.asyncio
async def test_an_employee_can_neither_read_nor_review(client, db_session, monkeypatch):
    """The employee role gets 403 on the list and on every review action — and nothing changes."""
    owner, h, _, suggestion_id, _ = await _org_with_suggestions(client, db_session, "ai_rt_emp@example.com")
    employee = await _invite_and_accept(client, monkeypatch, owner, "ai_rt_emp2@example.com", "employee")
    eh = _auth_header(employee["access_token"])

    assert (await client.get(SUGGESTIONS, headers=eh)).status_code == 403
    for action in ("approve", "reject"):
        assert (await client.post(f"{SUGGESTIONS}/{suggestion_id}/{action}", headers=eh)).status_code == 403
    assert (
        await client.post(f"{SUGGESTIONS}/{suggestion_id}/edit", json={"risk_level": "low"}, headers=eh)
    ).status_code == 403

    still_pending = await client.get(f"{SUGGESTIONS}?status=pending", headers=h)
    assert still_pending.json()["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_a_business_executive_can_read_and_review(client, db_session, monkeypatch):
    """Executives see the queue and can decide on it, same as an HR admin."""
    owner, _, _, suggestion_id, _ = await _org_with_suggestions(client, db_session, "ai_rt_exec@example.com")
    exec_ = await _invite_and_accept(client, monkeypatch, owner, "ai_rt_exec2@example.com", "business_executive")
    xh = _auth_header(exec_["access_token"])

    assert (await client.get(SUGGESTIONS, headers=xh)).status_code == 200
    resp = await client.post(f"{SUGGESTIONS}/{suggestion_id}/reject", headers=xh)
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_another_organizations_admin_sees_and_touches_nothing(client, db_session):
    """Tenant isolation: org B's HR admin gets an empty list and a 404 on org A's suggestion."""
    _, _, _, suggestion_id, _ = await _org_with_suggestions(client, db_session, "ai_rt_orga@example.com")
    other = await register_verified_and_login(client, email="ai_rt_orgb@example.com")
    bh = _auth_header(other["access_token"])

    assert (await client.get(SUGGESTIONS, headers=bh)).json()["pagination"]["total"] == 0
    for action in ("approve", "reject"):
        assert (await client.post(f"{SUGGESTIONS}/{suggestion_id}/{action}", headers=bh)).status_code == 404
    assert (
        await client.post(f"{SUGGESTIONS}/{suggestion_id}/edit", json={"risk_level": "low"}, headers=bh)
    ).status_code == 404
