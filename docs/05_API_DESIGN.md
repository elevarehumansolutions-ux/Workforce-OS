# API Design

Built directly on `02_SYSTEM_DESIGN.md` (module ownership) and `04_DATABASE.md` (schema). One endpoint list per module.

## Conventions

- **No `organization_id` anywhere in a URL.** It comes from the JWT, always, one source of truth. See `03_ARCHITECTURE.md` request lifecycle.
- **Resource filters are query parameters**, not baked into the path: `GET /tasks?department_id=<id>&status=open`, not `/departments/<id>/tasks`. A resource can be filtered by more than one thing (department, assignee, status, kpi), a rigid nested path only works cleanly for one axis at a time.
- **JSON everywhere. camelCase in the wire format, snake_case in the database/Python.** FastAPI/Pydantic can auto-convert at the boundary (an alias generator). This is purely cosmetic but matters for Uche, camelCase is idiomatic on the React side, snake_case is idiomatic on the Python/DB side, no reason to force either side to write unnatural code.
- **No `/v1` versioning prefix for MVP.** Versioning exists to let a backend change without breaking API consumers you can't coordinate with. Here, backend and frontend are one team, deployed together. Adding a version prefix now is solving a problem this project doesn't have yet, revisit if a public/partner API ever gets built.
- **Error shape, consistent everywhere:** flat, not nested — `{ "code": "VALIDATION_ERROR", "status": "error", "message": "...", "details": [] }` (`core/schemas.py`'s `ErrorResponse`; `details` is a list of `{field, message}`, populated for validation errors, empty otherwise). Corrected 2026-09-18 — this section previously documented a nested `{ "error": { ... } }` shape that was never actually implemented; the flat shape above is what M2's exception handlers genuinely return, confirmed against the real code, not just the original design intent. Status codes used conventionally: 400 (validation), 401 (not authenticated), 403 (authenticated but not allowed, the department-check failures from `03_ARCHITECTURE.md`), 404, 409 (conflict, e.g. KPI weights not summing to 100).
- **List endpoints are paginated** (cursor-based), never return an unbounded array.
- **State-changing business actions get their own endpoint, not a generic PATCH.** e.g. `POST /tasks/{id}/complete`, not `PATCH /tasks/{id}` with `{"status": "completed"}`. Reason: completing a task also has to set `completed_at` atomically and only from a valid prior status, a raw field-level PATCH would let a client set `status` to anything, bypassing that rule entirely. A dedicated action endpoint is where the one valid transition lives, in exactly one place, same principle as everything else in this project, one place a rule can live beats a field anyone can overwrite.

## Identity

- `POST /auth/register` — sign up. First person into a new org becomes Owner.
- `POST /auth/login` — returns access token (short-lived, org+role baked in) + refresh token.
- `POST /auth/refresh` — exchanges refresh token for a new access token; re-validates the membership is still active (this is the revocation check from `03_ARCHITECTURE.md`).
- `POST /auth/logout` — invalidates the refresh token.
- `GET /me` — current identity + all memberships (for org-switching).
- `POST /memberships` — invite a teammate (Owner/HR Administrator only).
- `PATCH /memberships/{id}` — change role or deactivate.
- `GET /memberships` — list the org's people.
- `GET /billing/history` — the org's own `billing_records`, Owner/HR Administrator only. Read-only, no invoice generation here, see `04_DATABASE.md`.
- `GET /ai-usage` — the org's own `ai_usage_log`, HR Administrator only. Token counts and estimated cost, per LLM call. Cross-org aggregate cost is internal-admin-script only, not an API endpoint.

## Org Structure

Mutations (`POST`/`PATCH`/`DELETE`, including offboard/reinstate) restricted to `hr_administrator`; `GET` (list and by-id) open to any authenticated org member. See `08_DECISIONS.md` 2026-09-21.

- `POST|GET /locations`, `GET|PATCH|DELETE /locations/{id}`
- `POST|GET /departments`, `GET|PATCH|DELETE /departments/{id}` (includes `is_critical`, `revenue_allocation_percentage`; `DELETE` blocked while active positions are still assigned, named reason, `08_DECISIONS.md` 2026-09-07)
- `POST|GET /positions`, `GET|PATCH|DELETE /positions/{id}` (`DELETE` blocked while active employees hold it or other positions report to it, named reason)
- `POST|GET /employees` (filter: `location_id`), `GET|PATCH /employees/{id}` — no `DELETE`, offboarding is the removal mechanism instead
- `POST /employees/{id}/offboard` — sets the employee inactive and deactivates their `Membership` if they have login access, in one step. Not a generic status PATCH. See `08_DECISIONS.md` 2026-09-20.
- `POST /employees/{id}/reinstate` — reverses an offboard: restores active status and re-enables login access if it was deactivated. See `08_DECISIONS.md` 2026-09-20.

## Business DNA

- `GET|PUT /business-dna` — one row per org, PUT upserts it. `PUT` is `hr_administrator`-only; `GET` is open to any authenticated org member. `PUT`'s request body also carries `organization_name`, which the service writes to `organizations.name` in the same transaction as the `business_dna` upsert (one audit-log entry) — see `08_DECISIONS.md` 2026-09-21. `GET`'s response resolves the org's name via the `organization_id` relationship, not a duplicated column.
- **Field-level restriction:** `capital_investment_amount` is included in `GET /business-dna`'s response only for `hr_administrator`/`business_executive` callers, omitted for everyone else. Every other field on the row is visible to any authenticated org member. See `08_DECISIONS.md` 2026-09-21 for why this is field-level, not a table-level role gate.
- `POST|GET /business-dna/core-values`, `PATCH|DELETE /business-dna/core-values/{id}` — mutations `hr_administrator`-only, reads open to any authenticated org member, same shape as the parent resource.

## OKR

- `POST|GET /okrs` (filter: `department_id`), `GET|PATCH /okrs/{id}`
- `POST|GET /okrs/{id}/key-results`, `PATCH /key-results/{id}`

## AI Suggestions

- `GET /ai-suggestions` (filter: `status`, `suggestion_type`)
- `POST /ai-suggestions/{id}/approve` — body optional. Empty body = approve as suggested (`status → approved`). Body with overriding fields = approve with corrections (`status → edited`). One endpoint, not two, because "approve" and "edit-then-approve" are the same action with an optional override, not two different actions. The server compares the body against `suggested_*` to decide which status to set and fills in `reviewed_*` either way, per the design already in `04_DATABASE.md`.
- `POST /ai-suggestions/{id}/reject`

## Performance

- `POST|GET /kpis` (filter: `department_id`, `location_id`), `PATCH /kpis/{id}`
- `POST /kpis/{id}/scores` — record a period's actual value, server computes `score_percentage`.
- `GET /kpis/{id}/scores` — historical scores for one KPI, direct access without going through the department rollup.
- `GET /departments/{id}/performance-summary` — the quarterly rollup that feeds dashboards.
- `GET /employees/leaderboard` (filter: `department_id`, `period`) — ranked employee scores, closes the drill-down gap in `01_REQUIREMENTS.md` §11.
- `GET /company-performance-summary` (filter: `period`) — bundles the headline dashboard section in one call: aggregate Company Performance Score, trend, Most Improved employee/department, and the stored `executive_summaries` narrative for that period. One endpoint, not four, since these all render together on the same dashboard section and a dashboard shouldn't make four round trips for one view.

## Audit Log

- `GET /audit-log` (filter: `entity_type`, `entity_id`, `actor_user_id`, date range) — read-only. No viewer screen required for MVP (see `07_SECURITY.md`), but the data needs to be reachable via API even without one, for support/debugging use.

## Task

- `POST /tasks` — standalone/ad hoc.
- `GET /tasks` (filter: `department_id`, `assigned_to_employee_id`, `status`, `kpi_id`, `overdue=true`)
- `GET|PATCH /tasks/{id}`
- `POST /tasks/{id}/complete`

## Workflow

- `POST|GET /workflow-templates`, `GET|PATCH /workflow-templates/{id}`
- `POST|GET /workflow-templates/{id}/steps`, `PATCH /workflow-steps/{id}`
- `POST /workflow-instances` — starts a case (body: `template_id`, `subject`)
- `GET /workflow-instances` (filter: `status`, `template_id`), `GET /workflow-instances/{id}`

## Attendance

- `POST /attendance/clock-in`, `POST /attendance/clock-out`
- `GET /attendance` (filter: `employee_id`, date range)

## Notifications

- `GET /notifications` (filter: `category`, `unread=true`)
- `POST /notifications/{id}/read`
