# Current Task

**M2 — Identity, Auth & Multi-Tenancy** (see `09_PROGRESS.md`)

**Backend implementation is functionally complete** — all auth endpoints,
memberships endpoints, and the full invite-teammate flow are built and
passing 64 tests under a genuinely RLS-enforcing DB role. See
`08_DECISIONS.md` 2026-09-17 entries for the full list of what shipped and
why.

## Immediate next step: none of this is committed yet

`git status` on `m2-identity-auth` shows a large amount of uncommitted work.
Per `CLAUDE.md`'s git workflow, before this milestone can be considered
closed: review the diff → commit → push → open PR → merge → delete the
branch → branch again for M3. None of that has happened yet — this is the
actual next action, not a new implementation task.

## After that, pick one:

1. **M2 frontend** — Registration, Login, org-switcher, Invite Teammate
   screen, Team Management screen (see `09_PROGRESS.md` M2 for the full
   list). Not started.
2. **M3 backend** (Audit Log & Notifications) — next milestone in dependency
   order, per `09_PROGRESS.md`.
3. **Known cleanup items, lower priority, not blocking either of the above:**
   - `tests/security/test_row_level_security*.py` (the M1 RLS regression
     suite) still fails — stale hardcoded connection string
     (`test_user:test_pass@localhost:5432/elevare_test`) that predates the
     real `.env`/`docker-compose.yml` setup, plus an outdated assumption
     that `organizations` has no RLS. Needs a rewrite against the real
     `elevare_app` role, not a small patch.
   - Dead `validate_phone_digits` function in `auth/schemas.py` — unused,
     safe to delete.
   - Open product question (not a bug): `PATCH /memberships/{id}` with
     `is_deactivated=True` deactivates the target's `User.account_status`
     globally, locking them out of every org they belong to, not just the
     one doing the deactivating. Needs a product decision (per-membership
     deactivation vs. global) before changing anything.

Depends on: M1 (done, see `09_PROGRESS.md`).
