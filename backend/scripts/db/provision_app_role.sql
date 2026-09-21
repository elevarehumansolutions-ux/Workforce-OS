-- Run once, manually, by the superuser (elevare) that owns the schema.
-- Creates the restricted role the live application (FastAPI, Celery worker,
-- Celery Beat) actually connects as for ordinary traffic. NOT a superuser,
-- NOT BYPASSRLS — RLS policies apply to it in full, which is the entire
-- point (07_SECURITY.md: "The main application role... never has
-- [BYPASSRLS], and never should"). Contrast with
-- scripts/admin/provision_platform_admin_role.sql, which provisions the
-- deliberately privileged, bypass-everything role for internal admin
-- scripts only — this one is its opposite number.
--
-- The db container has no access to this file directly (nothing mounts
-- backend/scripts/ into it), so pipe it in via stdin from the host instead
-- of using -f (which would look for the file inside the container).
-- The password is never written into this file — it's passed at
-- invocation time via psql's -v (variable substitution), sourced from
-- backend/scripts/db/.env.db (copy .env.db.example, fill in the real
-- value — should match elevare_app's password in the main .env's
-- DATABASE_URL). Kept in its own file, not the main .env, for the same
-- reason scripts/admin/.env.admin is separate: pydantic-settings'
-- Settings() would crash on an undeclared key, and this credential has
-- no reason to be readable by the running app/worker/beat containers.
-- e.g.:
--   set -a && source backend/scripts/db/.env.db && set +a
--   docker-compose exec -T db psql -U elevare -d elevare_db -v app_password="$ELEVARE_APP_DB_PASSWORD" < backend/scripts/db/provision_app_role.sql

-- Not a DO $$...$$ block: psql's -v substitution (:'app_password' below)
-- is deliberately skipped inside dollar-quoted strings, so the password
-- would reach Postgres as the literal text ":'app_password'", a syntax
-- error, not the actual value. \gexec keeps the same idempotency (a role
-- that already exists means zero rows, so nothing runs) while keeping the
-- substitution in an ordinary SQL statement, where it actually applies.
SELECT 'CREATE ROLE elevare_app WITH LOGIN PASSWORD ' || quote_literal(:'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'elevare_app')
\gexec

GRANT CONNECT ON DATABASE elevare_db TO elevare_app;
GRANT USAGE ON SCHEMA public TO elevare_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO elevare_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO elevare_app;

-- Applies automatically to tables/sequences created by future migrations
-- (run as `elevare`, the schema owner) — nobody has to remember to re-run
-- grants after every new migration.
ALTER DEFAULT PRIVILEGES FOR ROLE elevare IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO elevare_app;
ALTER DEFAULT PRIVILEGES FOR ROLE elevare IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO elevare_app;
