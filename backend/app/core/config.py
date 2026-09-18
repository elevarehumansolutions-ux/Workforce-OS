"""Application settings loaded from environment variables and a .env file"""

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_SECRET_KEY_VALUES = {
    "",
    "dev-secret-key-change-in-production",
    "change-me-in-production",
    "secret",
}


class Settings(BaseSettings):
    """Centralised configuration for the Workforce API.

    All values are read from environment variables (case-insensitive).
    A ``.env`` file in the working directory is loaded automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # MIGRATION_DATABASE_URL lives in the same .env but is deliberately
        # not a field on this class (see the note below) — without this,
        # pydantic-settings treats any env var with no matching field as a
        # validation error, not a harmless extra.
        extra="ignore",
    )

    # Application
    app_name: str = "Elevare Workforce API"
    app_version: str
    app_url: str
    debug: bool
    environment: str = "development"

    # --- Persistence ---
    # Main app DB role - RLS-scoped, never BYPASSRLS. Genuinely enforced as
    # of 08_DECISIONS.md 2026-09-17 — this must resolve to elevare_app
    # (scripts/db/provision_app_role.sql), not the elevare superuser that
    # docker-compose's POSTGRES_USER creates. Using the superuser here was a
    # real M1 gap: it silently bypassed every RLS policy in the app the
    # whole time, undetected until a test that relied on RLS alone (no
    # redundant app-level filter) caught it.
    database_url: str

    # NOTE: no migration_database_url field here, deliberately — Alembic is
    # the only consumer of that credential (see alembic/env.py, which reads
    # MIGRATION_DATABASE_URL straight from the environment). Keeping it off
    # Settings means this class only ever describes what the running
    # app/Celery processes themselves need.
    #
    # NOTE: no platform_admin_database_url field here, deliberately. That
    # credential lives in scripts/admin/.env.admin, read only by scripts/admin/
    # tooling via its own separate loader — never by this app's own
    # web/worker/beat processes. See 07_SECURITY.md. Declaring it here would
    # mean the app's own Settings requires a value it must never actually have.

    redis_url: str

    # JWT Security
    jwt_secret_key: str
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    # CORS
    cors_allowed_origins: list[str]

    # Email Verification
    email_stub_mode: bool = True
    email_verification_token_expiry: int = 24
    password_reset_token_expiry: int = 1

    # Email delivery (Resend — see 00_PROJECT_CONTEXT.md)
    resend_api_key: str | None = None
    mail_from: str = "Elevare Workforce OS <noreply@elevare.com>"
    invite_expiry: int = 7

    # Claude API KEY
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Paystack — primary payment provider (billing module)
    paystack_secret_key: str | None = None
    paystack_public_key: str | None = None

    @property
    def cookie_secure(self) -> bool:
        """Refresh-cookie Secure flag — derived from environment, not its own
        setting, so it can't drift out of sync with ENVIRONMENT. See
        03_ARCHITECTURE.md: true in staging/production, false in local dev.
        """
        return self.environment != "development"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Refuse to start in production with insecure default values."""
        if self.environment != "production":
            return self

        errors = []

        if (
            self.jwt_secret_key.lower() in _INSECURE_SECRET_KEY_VALUES
            or len(self.jwt_secret_key) < 32
        ):
            errors.append("JWT_SECRET_KEY is insecure or too short (min 32 chars)")

        if not self.cookie_secure:
            errors.append("COOKIE_SECURE must be true in production")

        if self.debug:
            errors.append("DEBUG must be false in production")

        if self.email_stub_mode:
            errors.append("EMAIL_STUB_MODE must be false in production")

        if any("localhost" in origin for origin in self.cors_allowed_origins):
            errors.append(
                "CORS_ORIGINS contains localhost — remove before production deploy"
            )

        if errors:
            raise ValueError(
                "Production security checks failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        return self


settings = Settings()

