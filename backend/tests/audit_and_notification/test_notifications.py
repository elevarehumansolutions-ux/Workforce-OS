"""HTTP-level tests for notification endpoints.

Covers GET /notifications, POST /notifications/{id}/read, and POST
/notifications/read-all.
"""
import pytest

from app.modules.audit_and_notification.enums import NotificationCategory
from app.modules.audit_and_notification.service import NotificationService

NOTIFICATIONS = "/api/v1/notifications"
MEMBERSHIPS = "/api/v1/memberships"
AUTH = "/api/v1/auth"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def _invite_and_accept(client, monkeypatch, owner, email: str, role: str) -> dict:
    from unittest.mock import MagicMock
    import app.modules.tenancy_identity.router as membership_router_module

    mock_dispatch = MagicMock()
    monkeypatch.setattr(membership_router_module, "dispatch_invite_email", mock_dispatch)

    await client.post(
        MEMBERSHIPS,
        json={"email": email, "role": role},
        headers=_auth_header(owner["access_token"]),
    )
    raw_token = mock_dispatch.delay.call_args.args[1].split("token=")[1]
    accept_resp = await client.post(
        f"{AUTH}/accept-invite",
        json={
            "token": raw_token,
            "full_name": "Test Teammate",
            "password": "Password123#",
            "confirm_password": "Password123#",
        },
    )
    return accept_resp.json()


@pytest.mark.asyncio
async def test_notifications_endpoints_require_authentication(client):
    """Both the list and mark-read endpoints return 401 without authentication."""
    resp1 = await client.get(NOTIFICATIONS)
    assert resp1.status_code == 401

    resp2 = await client.post(f"{NOTIFICATIONS}/00000000-0000-0000-0000-000000000000/read")
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_list_notifications_returns_only_own_stream(client, db_session, monkeypatch):
    """No role restriction, but must self-scope.

    One recipient must never see another recipient's notifications, even
    within the same org.
    """
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="notif_owner1@example.com")
    other = await _invite_and_accept(client, monkeypatch, owner, "notif_other1@example.com", "employee")

    await set_org_context(db_session, owner["organization"]["id"])
    service = NotificationService(db_session)
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="For owner",
    )
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[other["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="For other",
    )

    resp = await client.get(NOTIFICATIONS, headers=_auth_header(owner["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "For owner"


@pytest.mark.asyncio
async def test_list_notifications_filters_by_category(client, db_session):
    """The category query param returns only notifications of that category."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="notif_owner2@example.com")
    await set_org_context(db_session, owner["organization"]["id"])
    service = NotificationService(db_session)

    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.TASK,
        title="Task notice",
    )
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="System notice",
    )

    resp = await client.get(
        NOTIFICATIONS,
        params={"category": "task"},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["category"] == "task"


@pytest.mark.asyncio
async def test_list_notifications_filters_by_unread(client, db_session):
    """The unread=True query param excludes notifications that have already been marked read."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="notif_owner3@example.com")
    await set_org_context(db_session, owner["organization"]["id"])
    service = NotificationService(db_session)

    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Unread one",
    )
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Will be read",
    )

    all_resp = await client.get(NOTIFICATIONS, headers=_auth_header(owner["access_token"]))
    to_mark = next(n for n in all_resp.json() if n["title"] == "Will be read")
    await client.post(
        f"{NOTIFICATIONS}/{to_mark['id']}/read",
        headers=_auth_header(owner["access_token"]),
    )

    resp = await client.get(
        NOTIFICATIONS,
        params={"unread": True},
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Unread one"


@pytest.mark.asyncio
async def test_mark_notification_read_updates_read_at(client, db_session):
    """Marking a notification read sets read_at from null to a timestamp."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="notif_owner4@example.com")
    await set_org_context(db_session, owner["organization"]["id"])
    await NotificationService(db_session).notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Mark me",
    )

    list_resp = await client.get(NOTIFICATIONS, headers=_auth_header(owner["access_token"]))
    notification_id = list_resp.json()[0]["id"]
    assert list_resp.json()[0]["read_at"] is None

    resp = await client.post(
        f"{NOTIFICATIONS}/{notification_id}/read",
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["read_at"] is not None


@pytest.mark.asyncio
async def test_mark_notification_read_rejects_someone_elses_notification(client, db_session, monkeypatch):
    """Marking read a notification that belongs to another recipient returns 404."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="notif_owner5@example.com")
    other = await _invite_and_accept(client, monkeypatch, owner, "notif_other5@example.com", "employee")

    await set_org_context(db_session, owner["organization"]["id"])
    await NotificationService(db_session).notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Owner's own",
    )
    list_resp = await client.get(NOTIFICATIONS, headers=_auth_header(owner["access_token"]))
    owners_notification_id = list_resp.json()[0]["id"]

    resp = await client.post(
        f"{NOTIFICATIONS}/{owners_notification_id}/read",
        headers=_auth_header(other["access_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_notification_read_rejects_unknown_id(client):
    """Marking read a notification id that doesn't exist returns 404."""
    from tests.conftest import register_verified_and_login

    owner = await register_verified_and_login(client, email="notif_owner6@example.com")

    resp = await client.post(
        f"{NOTIFICATIONS}/00000000-0000-0000-0000-000000000000/read",
        headers=_auth_header(owner["access_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read_marks_only_own_unread(client, db_session, monkeypatch):
    """Mark-all-read marks only the caller's own unread notifications, leaving other recipients' untouched."""
    from tests.conftest import register_verified_and_login, set_org_context

    owner = await register_verified_and_login(client, email="notif_owner7@example.com")
    other = await _invite_and_accept(client, monkeypatch, owner, "notif_other7@example.com", "employee")

    await set_org_context(db_session, owner["organization"]["id"])
    service = NotificationService(db_session)
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Owner unread 1",
    )
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[owner["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Owner unread 2",
    )
    await service.notify(
        organization_id=owner["organization"]["id"],
        recipient_user_ids=[other["user"]["id"]],
        category=NotificationCategory.SYSTEM,
        title="Other's own, must stay untouched",
    )

    resp = await client.post(f"{NOTIFICATIONS}/read-all", headers=_auth_header(owner["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["marked_read"] == 2

    owner_unread = await client.get(
        NOTIFICATIONS, params={"unread": True}, headers=_auth_header(owner["access_token"])
    )
    assert owner_unread.json() == []

    other_unread = await client.get(
        NOTIFICATIONS, params={"unread": True}, headers=_auth_header(other["access_token"])
    )
    assert len(other_unread.json()) == 1
    assert other_unread.json()[0]["title"] == "Other's own, must stay untouched"
