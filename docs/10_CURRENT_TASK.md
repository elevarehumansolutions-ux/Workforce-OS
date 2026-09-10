# Current Task

**M2 — Identity, Auth & Multi-Tenancy** (see `09_PROGRESS.md`)

Backend: `organizations` (incl. `fiscal_year_start_month`, `DEFAULT 1`), `users`, `memberships` (`04_DATABASE.md` Cluster 1) + RLS policies + the `SET LOCAL app.current_org_id` tenant-context FastAPI dependency (`03_ARCHITECTURE.md`). `POST /auth/register|login|refresh|logout`, `GET /me`, `POST/PATCH/GET /memberships`. Password hashing (bcrypt/argon2). JWT with baked-in `organization_id`/`role`, short-lived access + refresh token, refresh re-validates live membership.

Frontend: Registration (identity-only: name, work email, password), Login, token storage (access in `localStorage`, refresh as `httpOnly` cookie), org-switcher (for multi-membership `GET /me`), Invite Teammate screen, and the separate Team Management screen (`GET /memberships`, role change/deactivation via `PATCH /memberships/{id}`).

Depends on: M1 (done, see `09_PROGRESS.md`).

Note: `backend/app/core/dependencies.py` already has `get_current_user`, `require_role`, `require_org_role` stubbed out (commented) from M1 scaffolding — this is where they get implemented for real, once the JWT handler and `User` model exist.
