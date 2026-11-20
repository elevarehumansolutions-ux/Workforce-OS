"""A customer company may never hand out Elevare's own platform role (``system_administrator``).

It is the platform operator's role (08_DECISIONS.md 2026-09-02), not a customer role. Every request
that takes a role uses ``CustomerRole``, which leaves it out, so the server answers 422.
"""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.organization.schemas import EmployeeCreateRequest, EmployeeGrantLoginRequest
from app.modules.tenancy_identity.schemas import (
    InviteTeammateRequest,
    ReactivateMembershipRequest,
    UpdateMembershipRequest,
)
from tests.conftest import register_verified_and_login

MEMBERSHIPS = "/api/v1/memberships"
PLATFORM_ROLE = "system_administrator"


def test_every_request_that_takes_a_role_refuses_the_platform_role():
    """All five request shapes reject it, and each still accepts an ordinary role."""
    refused = [
        lambda role: InviteTeammateRequest(email="a@example.com", role=role),
        lambda role: ReactivateMembershipRequest(role=role),
        lambda role: UpdateMembershipRequest(role=role),
        lambda role: EmployeeGrantLoginRequest(role=role),
        lambda role: EmployeeCreateRequest(
            position_id=uuid.uuid4(), first_name="A", last_name="B", work_email="a@example.com",
            start_date=date(2026, 1, 1), grant_login_access=True, role=role,
        ),
    ]
    for build in refused:
        build("manager")  # an ordinary role is fine
        with pytest.raises(ValidationError):
            build(PLATFORM_ROLE)


@pytest.mark.asyncio
async def test_inviting_with_the_platform_role_answers_422_and_a_normal_role_still_works(client):
    owner = await register_verified_and_login(client, email="plat_owner@example.com")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}

    refused = await client.post(
        MEMBERSHIPS, json={"email": "plat_mate@example.com", "role": PLATFORM_ROLE}, headers=headers
    )
    allowed = await client.post(
        MEMBERSHIPS, json={"email": "plat_mate@example.com", "role": "manager"}, headers=headers
    )

    assert refused.status_code == 422, refused.text
    assert allowed.status_code == 200, allowed.text
