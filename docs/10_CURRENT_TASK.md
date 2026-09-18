# Current Task

**M3 — Audit Log & Notifications** (infrastructure modules, see `09_PROGRESS.md`)

M2 backend is merged to `main` (PRs #2, #3) and closed out — see
`08_DECISIONS.md` 2026-09-17/09-18 entries. Branched `m3-audit-notifications`
off the updated `main`.

**Backend:** `audit_log`, `notifications` tables (`04_DATABASE.md` Clusters
8–9). Internal `log_action()` / `notify()` services — the ones every later
domain module calls into, built now, ahead of the modules that need them
(per the 2026-09-06 decision that uninstrumented write paths can't be
retrofitted). `GET /audit-log` (no viewer UI required), `GET /notifications`
(filters: `category`, `unread=true`), `POST /notifications/{id}/read`.

**Frontend:** Notification bell/center (role-filtered stream, category
filter, mark-read). No audit log viewer screen (explicitly deferred,
`07_SECURITY.md`).

**Completeness gaps already flagged for this milestone (09_PROGRESS.md,
2026-09-18 review) — worth deciding before or during the build, not after:**
- `GET /audit-log` has no stated filtering (`entity_type`, `entity_id`,
  actor, date range) or pagination. Given every mutating action across every
  future module writes to this table, it's the fastest-growing table in the
  schema — an unfiltered, unpaginated endpoint over it won't hold up. Use
  `core/pagination.py`'s cursor-based `paginate_cursor` here (the
  append-heavy, large-feed case it was actually built for — see
  `08_DECISIONS.md` 2026-09-18 on why `GET /memberships` used offset
  pagination instead; this endpoint is the opposite shape).
- `POST /notifications/{id}/read` has no bulk "mark all as read."

**Resolved, unrelated to M3:** Uche's Next.js question came back — client-rendered only, no architecture change needed (`08_DECISIONS.md` 2026-09-18). Small pending action, not urgent: add his real frontend URL (Vercel) to `CORS_ALLOWED_ORIGINS` once it exists.

**Depends on:** M2 (needs `actor_user_id`/`recipient_user_id` — done).
