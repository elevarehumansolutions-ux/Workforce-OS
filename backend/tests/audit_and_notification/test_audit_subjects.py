"""What an audit row was about, in words (Recent activity: "added Chidi Okafor (chidi@x.com)")."""
import pytest

from app.modules.audit_and_notification.service import AuditService
from app.modules.audit_and_notification.subjects import label_from_changes
from tests.audit_and_notification.test_audit_log import AUDIT_LOG, _auth_header
from tests.conftest import register_verified_and_login, set_org_context

import uuid


def test_an_employee_row_reads_as_name_and_email():
    changes = {"old": None, "new": {"first_name": "Chidi", "last_name": "Okafor", "work_email": "chidi@x.com"}}
    assert label_from_changes("employee", changes) == "Chidi Okafor (chidi@x.com)"


def test_an_invite_row_reads_as_the_email():
    assert label_from_changes("invite", {"old": None, "new": {"email": "a@x.com", "role": "manager"}}) == "a@x.com"


def test_a_deleted_thing_is_named_from_its_old_side():
    assert label_from_changes("department", {"old": {"name": "Sales"}, "new": None}) == "Sales"


def test_a_row_with_only_a_changed_field_has_no_name_in_it():
    assert label_from_changes("kpi", {"old": {"weight": "60"}, "new": {"weight": "40"}}) is None
    assert label_from_changes("kpi", None) is None


@pytest.mark.asyncio
async def test_the_api_names_what_each_row_was_about(client, db_session):
    """One row stored the name; one only stored a changed field, so the department's name is looked up."""
    owner = await register_verified_and_login(client, email="subj_owner@example.com")
    headers = _auth_header(owner["access_token"])
    department = (await client.post("/api/v1/departments", json={"name": "Sales"}, headers=headers)).json()

    await set_org_context(db_session, owner["organization"]["id"])
    service = AuditService(db_session)
    await service.log_action(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="create",
        entity_type="employee",
        entity_id=uuid.uuid4(),
        changes={"old": None, "new": {"first_name": "Chidi", "last_name": "Okafor", "work_email": "chidi@x.com"}},
    )
    await service.log_action(
        organization_id=owner["organization"]["id"],
        actor_user_id=owner["user"]["id"],
        action="update",
        entity_type="department",
        entity_id=uuid.UUID(department["id"]),
        changes={"old": {"is_critical": False}, "new": {"is_critical": True}},
    )

    rows = (await client.get(AUDIT_LOG, headers=headers)).json()["data"]
    subject_of = {(row["entity_type"], row["action"]): row["subject"] for row in rows}

    assert subject_of[("employee", "create")] == "Chidi Okafor (chidi@x.com)"
    assert subject_of[("department", "update")] == "Sales"
