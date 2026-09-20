"""Shared pytest fixtures and factory helpers for the Elevare Workforce test suite."""
from app.modules.tenancy_identity.enums import AccountStatus
from app.modules.auth.schemas import RegisterRequest
from app.modules.tenancy_identity.enums import AuthProvider
from datetime import datetime, UTC, timedelta
from uuid import uuid4
import pytest_asyncio
from app.core.database import AsyncSessionLocal


import app.core.model_registry  #noqa:  F401
from app.core.config import settings
from app.core.dependencies import get_db

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.modules.tenancy_identity.models import User

test_engine = create_async_engine(settings.database_url, poolclass=NullPool)


def make_user(**overrides) -> User:
    """Create a User ORM instance with test defaults."""

    data = {
        "email": f"user_{uuid4().hex[:8]}@example.com",
        "full_name": "John Doe",
        "password_hash": "hashed_password",
        "auth_provider": AuthProvider.PASSWORD.value,
        "account_status": AccountStatus.VERIFIED.value,
    }

    data.update(overrides)

    return User(**data)

def make_register_data(**overrides) -> RegisterRequest:
    """Build a RegisterRequest with unique email/phone and sensible defaults."""
    defaults = {
        "full_name": "John Doe",
        "email": f"user_{uuid4().hex[:8]}@example.com",
        "password": "Password123#",
        "confirm_password": "Password123#",
    }
    defaults.update(overrides)
    return RegisterRequest(**defaults)


def register_payload(**overrides) -> dict:
    """Build a raw register-request dict for HTTP-level tests.

    Deliberately not ``make_register_data(...).model_dump()`` — RegisterRequest
    declares ``confirm_password`` with ``exclude=True``, so dumping a built
    instance silently drops it. A real client still has to send it on the
    wire; this stays a plain dict for that reason.
    """
    defaults = {
        "full_name": "John Doe",
        "email": f"user_{uuid4().hex[:8]}@example.com",
        "password": "Password123#",
        "confirm_password": "Password123#",
    }
    defaults.update(overrides)
    return defaults

@pytest_asyncio.fixture
async def db_session():
    """
    Provide a DB session that rolls back after each test.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        async with AsyncSessionLocal(bind=conn, expire_on_commit=False) as session:
            yield session
        await conn.rollback()


async def set_org_context(db_session: AsyncSession, organization_id) -> None:
    """Explicitly (re)establish RLS tenant context on a raw ``db_session``,
    mirroring ``core/dependencies.py``'s ``get_current_membership``.

    Needed when a test seeds rows directly via a service/repository rather
    than through an authenticated client request — a real request sets this
    itself, per request, from the caller's JWT.
    """
    await db_session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )


async def register_verified_and_login(client, **overrides) -> dict:
    """Register, verify, and log in a user via the real HTTP endpoints.

    Returns login's JSON body (user/organization/membership/access_token) —
    everything a test needs to act as a real, verified, logged-in founder
    without repeating the same three-call setup in every test.
    """
    payload = register_payload(**overrides)
    reg_resp = await client.post("/api/v1/auth/register", json=payload)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"token": reg_resp.json()["verification_token"]},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    return login_resp.json()


@pytest_asyncio.fixture
async def client(db_session):
    """
    An httpx client that drives the real FastAPI app (real routing, request
    validation, dependency injection — not calling AuthService directly).
    ``get_db`` is overridden to hand every request the same rolled-back
    ``db_session`` used elsewhere, so router-level tests stay isolated
    without needing a second database.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
