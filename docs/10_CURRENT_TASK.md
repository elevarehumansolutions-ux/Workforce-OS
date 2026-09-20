# Current Task

**M3 — Audit Log & Notifications** (infrastructure modules, see `09_PROGRESS.md`)

Backend is done and verified (2026-09-20) on `m3-audit-notifications` — full
design writeup in `08_DECISIONS.md` 2026-09-20. Not yet committed/pushed/PR'd
— that's the next mechanical step, same as M2's "commit → review → PR →
merge" flow (`08_DECISIONS.md`/`09_PROGRESS.md`).

**Backend, shipped:** `audit_log`/`notifications` tables + RLS policies
(`04_DATABASE.md` Clusters 8–9), `log_action()`/`notify()` internal services,
all four endpoints (`GET /audit-log`, `GET /notifications`,
`POST /notifications/{id}/read`, `POST /notifications/read-all`). Both
completeness gaps flagged in the 2026-09-18 review — `GET /audit-log`'s
missing filters/pagination, and bulk mark-all-read — are closed. 16 new
tests (`tests/audit_and_notification/`), 90 tests passing total, run
against the real dev DB (not just reasoned about).

**Backend, not yet done:** nothing outstanding — see `08_DECISIONS.md`
2026-09-20 for the full list of what shipped in this pass.

**Frontend:** Notification bell/center (role-filtered stream, category
filter, mark-read). Not started. No audit log viewer screen needed
(explicitly deferred, `07_SECURITY.md`).

**Depends on:** M2 (`actor_user_id`/`recipient_user_id` — done).

## Next recommended action

1. Review the diff on `m3-audit-notifications`, commit, push, open a PR,
   merge, delete the branch (local + remote) per the standard workflow.
2. Decide: M3 frontend (notification bell), or move on to M4 (Org
   Structure) backend — both are unblocked at this point.
3. Before M4 starts: `09_PROGRESS.md`'s M4 entry already flags an open
   cross-module question (does offboarding an employee also deactivate
   their `Membership`?) that needs a decision before that milestone's
   design is settled, not discovered mid-build.
