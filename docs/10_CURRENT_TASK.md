# Current Task

**M1 — Foundation & Infrastructure Scaffolding** (see `09_PROGRESS.md`)

Backend: repo/module skeleton, one Dockerfile with three containers (uvicorn/celery worker/celery beat), Postgres + Alembic, Redis, Celery wiring, FastAPI entrypoint + router aggregation, CORS middleware, `.env`/`.env.example`, the RLS regression test suite (`tests/security/`). Also: the `platform_admin` Postgres role (`BYPASSRLS`), separate credential from the main app's `.env`, usable only from `scripts/admin/`, never the web/worker/beat containers — provisioned now, alongside RLS itself, so later milestones (Audit Log's admin-script logging, Billing's manual admin scripts) have it ready rather than needing it created retroactively.

Frontend: Vite/React scaffold, API client, env config — parallel track, no shared blocker with backend yet.

Depends on: nothing. This is the starting point.
