# Current Task

**M4 — Org Structure** (see `09_PROGRESS.md`)

M3 backend is merged to `main` (PR #5) and closed out — see `08_DECISIONS.md`
2026-09-20. `m3-audit-notifications` deleted (local + remote). Branched
`m4-org-structure` off the updated `main`. M3 frontend (notification
bell/center) is Uche's track, not blocking this milestone.

**Backend:** `locations`, `departments`, `positions`, `employees`
(`04_DATABASE.md` Cluster 2). CRUD endpoints, `is_critical` toggle on
departments, `reports_to_position_id` vs `employees.manager_id`, location
filter + index, delete-blocked-while-referenced rule for `departments`/
`positions` (named reason — a real hard delete, unchanged from the
2026-09-07 rule), audit-log calls on every mutation (via M3's
`log_action()`).

**Employee offboarding/reinstatement — both resolved (2026-09-20), see
`08_DECISIONS.md`:**
- `POST /employees/{id}/offboard` (a dedicated action, not a generic status
  PATCH) sets `employees.status = 'inactive'` and, if the employee has a
  `Membership`, deactivates it (`deactivated_at`) in the same transaction —
  both logged to `audit_log`. Automatic, not a separate manual step,
  matching how real enterprise identity/HR systems (Okta Lifecycle
  Management, Workday leaver workflows) deprovision access on termination.
- Does **not** block on the employee having direct reports
  (`employees.manager_id`) — offboarding is a soft, reversible status
  change, not a delete, so nothing actually becomes a dangling FK. Reports
  simply keep pointing at the now-inactive manager until reassigned; no
  forced-reassignment prompt in MVP.
- `POST /employees/{id}/reinstate` — mirror action, reverses an offboard
  (`status = 'active'`, un-deactivates the `Membership`), reusing the same
  reactivation mechanism M2 already built for re-inviting a previously
  deactivated teammate.
- This is distinct from, and doesn't change, the delete-blocked-while-
  referenced rule for actually *deleting* a `positions` row — that's a real
  hard delete and stays blocked.

**Still open:**
- **Pre-existing, re-surfacing now that M4 is underway:** `01_REQUIREMENTS.md`
  §1 flags the Business DNA questionnaire as materially narrower in the
  discovery notes than in the PRD's field list. Doesn't block M4, but M5 is
  next after this and needs that confirmed before it starts, not discovered
  mid-build.

**Frontend:** Org setup screens — Departments (with Critical toggle),
Positions/job architecture, Locations, Employee Directory + Add Employee
(grant-login-access checkbox, Reporting Manager field, location filter),
Offboard/Reinstate Employee actions. Not started.

**Depends on:** M2, M3 (both done).

## Next recommended action

1. Build M4 backend: `locations`/`departments`/`positions`/`employees`
   models, RLS policies, CRUD endpoints, offboard/reinstate actions,
   delete-block rule for departments/positions, audit-log wiring.
2. Standard workflow once done: review → commit → push → PR → merge →
   delete branch → branch `m5-business-dna`, but confirm the Business DNA
   questionnaire gap above before that milestone actually starts.
