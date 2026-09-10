-- Run once, manually, by a superuser - never by the app itself.
-- The db container has no access to this file directly (nothing mounts
-- backend/scripts/ into it), so pipe it in via stdin from the host instead
-- of using -f (which would look for the file inside the container).
-- e.g.: docker-compose exec -T db psql -U elevare -d elevare_db < backend/scripts/admin/provision_platform_admin_role.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'elevare_platform_admin') THEN
        CREATE ROLE elevare_platform_admin WITH LOGIN PASSWORD 'changeme-generate-a-real-secret' BYPASSRLS;
    END IF;
END
$$;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO elevare_platform_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO elevare_platform_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO elevare_platform_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO elevare_platform_admin;