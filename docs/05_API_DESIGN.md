# API Design

Built directly on `02_SYSTEM_DESIGN.md` (module ownership) and `04_DATABASE.md` (schema). One endpoint list per module.

**For Uche: use this alongside `GET /docs` (Swagger UI, only served when `DEBUG=true`), not instead of it.** This doc is the *shape* of the API — which endpoints exist, who's allowed to call them, and why they're designed the way they are. `/docs` is the *exact* request/response schema for each one — every field, its type, and whether it's required — generated straight from the real Pydantic models, so it can never drift from the code the way a hand-maintained doc can. If the two ever disagree, `/docs` is right; flag it so this file gets corrected.

**Audited against the real router code on 2026-09-28** (every `@router` decorator across every mounted module, cross-checked line by line against this file) — see `08_DECISIONS.md` 2026-09-28 for what was wrong before this pass and why it mattered.

## Conventions — read this section first

- **The wire format is snake_case, not camelCase — corrected 2026-09-28.** This section previously said the API auto-converts to camelCase via a Pydantic alias generator. That was never actually implemented: every schema in the codebase (`LocationResponse`, `DepartmentCreateRequest`, every AI suggestion schema, all of them) uses a plain field name with no `alias_generator` anywhere. **If your frontend code sends or expects camelCase keys (`positionId`, `isCritical`, `revenueAllocationPercentage`), those requests are being silently accepted with the field ignored (FastAPI ignores unrecognized JSON keys by default) rather than rejected — so a request can return 200 while quietly not doing what you asked.** Every field, in every request and response body, is snake_case: `position_id`, `is_critical`, `revenue_allocation_percentage`, `created_at`, and so on — matching Python and the database exactly, no translation layer at all. **This is worth checking your existing API calls against before anything else in this doc.**
- **No `organization_id` anywhere in a URL.** It comes from the JWT, always, one source of truth. Don't put it in a request body either — the server ignores any `organization_id` a client sends and always uses the one from the caller's own token.
- **Every route in this doc is mounted under `/api/v1`.** `GET /me` in this doc means `GET /api/v1/me` on the wire — kept off the paths below for readability, don't drop it from real calls.
- **Resource filters are query parameters**, not baked into the path: `GET /tasks?department_id=<id>&status=open`, not `/departments/<id>/tasks`.
- **Error shape, consistent everywhere:** flat, not nested —
  ```json
  { "code": "VALIDATION_ERROR", "status": "error", "message": "...", "details": [] }
  ```
  (`core/schemas.py`'s `ErrorResponse`; `details` is a list of `{field, message}`, populated for validation errors, empty otherwise). Status codes used conventionally: **400** validation, **401** not authenticated (missing/expired token — redirect to login), **403** authenticated but not allowed (wrong role — show a permission message, don't redirect to login), **404** not found or not visible to this org, **409** conflict (a duplicate name, or acting on something already decided, e.g. approving a suggestion twice).
- **Most list endpoints are offset-paginated**: `page`/`limit` query params (1-indexed, `limit` typically capped at 100), response shape:
  ```json
  { "data": [...], "pagination": { "page": 1, "limit": 20, "total": 42, "total_pages": 3 } }
  ```
  The Audit Log is the one exception — cursor-paginated (`cursor`/`limit` query params, a `next_cursor` in the response instead of a page number), since that list can grow unbounded.
- **Auth:** every endpoint except `POST /auth/register|login|refresh|forgot-password|reset-password|accept-invite` requires `Authorization: Bearer <access_token>`. The refresh token travels as an httpOnly cookie, not a header — the frontend never reads or stores it directly, just calls `POST /auth/refresh` when the access token expires and lets the cookie do the work.
- **State-changing business actions get their own endpoint, not a generic PATCH.** e.g. `POST /employees/{id}/offboard`, not `PATCH /employees/{id}` with a status field.
- **Some write endpoints trigger AI suggestion generation as an async side effect, invisible in the response.** Marking a department critical, adding a position, or saving a new OKR each enqueue a background job (a few seconds to a couple of minutes later, never blocking the request). The endpoint's own response never reflects this — poll `GET /ai-suggestions` separately if the UI needs to show new ones arriving, don't expect them synchronously after the triggering call.

## What's actually live right now

Only **seven modules** are mounted in `main.py` today: Identity/Memberships, Org Structure, Business DNA, OKR, AI Suggestions, Audit Log, Notifications. Everything under "Not yet built" further down (Performance/KPIs, Task, Workflow, Attendance) is designed but **returns 404 today, not a stub** — check `09_PROGRESS.md` for which milestone ships each one before building against it.

## Identity

**Auth** (`/auth/...`, all shipped in M2):
- `POST /auth/register` — sign up. First person into a new org becomes Owner (stored as an `hr_administrator` membership — there's no separate "Owner" role value anywhere in the system; see the Org Structure note below).
- `POST /auth/verify-email` — completes registration using the token from the verification email.
- `POST /auth/resend-verification` — request a new verification email. Always returns a generic success message, regardless of whether the email exists or is already verified (don't use the response to tell a user "that email isn't registered").
- `POST /auth/login` — returns an access token (short-lived, org+role baked in) + sets the refresh cookie.
- `POST /auth/refresh` — exchanges the refresh cookie for a new access token; re-validates the membership is still active (so a deactivated teammate is logged out on their next silent refresh, not just their next login).
- `POST /auth/logout` — revokes the current refresh token and clears the cookie.
- `POST /auth/change-password` — the logged-in user's own password change (requires the bearer token, not a separate reset flow).
- `POST /auth/forgot-password` — request a reset link. Same generic-message reasoning as resend-verification.
- `POST /auth/reset-password` — completes a reset using the token from that email.
- `POST /auth/accept-invite` — completes a teammate invite for an email with no prior account; creates the account and logs straight in, same response shape as `/register`.
- `GET /me` — current identity + every organization the caller belongs to. This is what feeds an org-switcher for a user with more than one membership.

**Memberships** (`/memberships`, shipped in M2):
- `POST /memberships` — add an existing user immediately, or invite an email with no account. **HR Administrator only** — not "Owner or HR Administrator": the founder is always registered *as* `hr_administrator`, so gating on that one role already covers them.
- `GET /memberships` — list the org's people, offset-paginated. **HR Administrator only** — not open to every member, unlike most `GET` endpoints in this API.
- `PATCH /memberships/{id}` — change a teammate's role and/or deactivate/reactivate them. **HR Administrator only.** A caller can't target their own membership this way, and can't deactivate the org's Owner.

**Not yet built:** `GET /billing/history` and `GET /ai-usage`. Both are designed (see `04_DATABASE.md`) but neither is mounted in the code today — calling them 404s. `GET /ai-usage` ships in **M8**; its screen doesn't land until M13 (paired with Billing History). `GET /billing/history`'s own backend milestone isn't scheduled yet as of this audit.

## Org Structure

Mutations (`POST`/`PATCH`/`DELETE`, including offboard/reinstate) restricted to `hr_administrator`; `GET` (list and by-id) open to any authenticated org member.

- `POST|GET /locations`, `GET|PATCH|DELETE /locations/{id}`
- `POST|GET /departments`, `GET|PATCH|DELETE /departments/{id}` — includes `is_critical`, `revenue_allocation_percentage`. `DELETE` returns **409** while active positions are still assigned, or a pending AI suggestion still targets it (the response's `message` names which reason(s) apply). `POST`/`PATCH` return **409** if the name duplicates another non-deleted department in the org (compared case/spacing/Unicode-insensitively — `"Sales"` and `"  sales "` collide). **Creating a department with `is_critical: true`, or updating one to become critical, enqueues AI suggestion generation** (see the Conventions note above).
- `POST|GET /positions`, `GET|PATCH|DELETE /positions/{id}` — `DELETE` returns **409** while active employees hold it, other positions report to it, or a pending AI suggestion still targets it. **Every `POST /positions` enqueues AI suggestion generation**, unconditionally, regardless of whether its department is critical.
- `POST|GET /employees` (filter: `location_id`), `GET|PATCH /employees/{id}` — no `DELETE`; offboarding is the removal mechanism instead.
- `POST /employees/{id}/offboard` — sets the employee inactive and deactivates their `Membership` if they have login access, in one step. Not a generic status PATCH.
- `POST /employees/{id}/reinstate` — reverses an offboard: restores active status and re-enables login access if it was deactivated.

## Business DNA

- `GET|PUT /business-dna` — one row per org; `PUT` upserts (works for both the first save and every later edit, no separate create/update). `PUT` is `hr_administrator`-only; `GET` is open to any authenticated org member. `PUT`'s body also carries `organization_name`, written through to `organizations.name` in the same transaction.
- **Field-level restriction, not a role gate on the whole endpoint:** `capital_investment_amount` in `GET /business-dna`'s response is `null` for every role except `hr_administrator`/`business_executive` — never a 403, the field is just empty for everyone else.
- `POST|GET /business-dna/core-values`, `PATCH|DELETE /business-dna/core-values/{id}` — mutations `hr_administrator`-only, reads open to any authenticated org member. `DELETE` is a genuine hard delete (**204, no body**) — the one place in this whole API that isn't a soft delete.

## OKR

`POST`/`PATCH` on `okrs` and `key_results` restricted to `hr_administrator`; `GET` open to any authenticated org member. No `DELETE` yet — deferred to M8.

- `POST|GET /okrs` (filter: `department_id`, `location_id`), `GET|PATCH /okrs/{id}`. **`POST /okrs` enqueues AI suggestion generation** (a new objective is prompt context for the `missing_department` suggestion type); editing an existing OKR does not.
- `POST|GET /okrs/{id}/key-results`, `PATCH /key-results/{id}` — same role gate and pagination envelope as the parent resource.

## AI Suggestions

- `GET /ai-suggestions` (filter: `status`, `suggestion_type`; `page`/`limit` offset pagination, newest first) — **HR Administrator or Business Executive.** Review actions below are open to the **same two roles**.
- `POST /ai-suggestions/{id}/approve` — **no body.** Approves exactly as the AI proposed (`status → approved`) and applies it to the real position/department.
- `POST /ai-suggestions/{id}/edit` — body: only the fields the reviewer is *changing* (`criticality_type`, `risk_level` for a `critical_position`; `revenue_allocation_percentage` for a `revenue_allocation`; `department_name` for a `missing_department`); anything left out keeps the AI's own value. `status → edited`, then applied. **422** if a field doesn't apply to the suggestion's type, if the body is empty, or if every supplied value equals the AI's own (that's an approve — call `/approve` instead). **The frontend must diff the form and send only the fields that actually changed** — resending the whole form as "the edit" will 422 whenever the reviewer didn't change anything.
- `POST /ai-suggestions/{id}/reject` — no body. Starts a quarterly suppression, so the same suggestion isn't proposed again this fiscal quarter. **404** if not visible to the caller's org; **409** if already reviewed (applies to approve/edit/reject alike — a second reviewer clicking the same button gets 409, not a silent overwrite).

**Decision rule for the frontend, worth building into the UI directly:** if nothing on the form changed from the AI's proposal, call `/approve`. If anything changed, call `/edit` with only the changed fields. Don't always call `/edit` "to be safe" — an edit with nothing changed 422s by design.

## Audit Log

- `GET /audit-log` (filter: `entity_type`, `entity_id`, `actor_user_id`, `date_from`, `date_to`; `cursor`/`limit`, cursor-paginated) — **HR Administrator or Business Executive only**, not open to every member. No dedicated viewer screen required for MVP, but reachable via API for support/debugging use.

## Notifications

- `GET /notifications` (filter: `category`, `unread=true`) — the caller's own stream, self-scoped by recipient, open to every role.
- `POST /notifications/{id}/read` — mark one of the caller's own notifications read.
- `POST /notifications/read-all` — mark every one of the caller's unread notifications read in one call; returns `{"marked_read": <count>}`.

---

## Not yet built — designed, not mounted in the code

Nothing below this line exists as a real endpoint today — every path here 404s. These sections describe the intended shape for whichever milestone eventually builds them; check `09_PROGRESS.md` before writing frontend code against any of them, and don't scaffold API client code for these yet, since the shape may still change before it's actually built.

### Performance (M8+)

- `POST|GET /kpis` (filter: `department_id`, `location_id`), `PATCH /kpis/{id}` — single-KPI create/read/edit; create and edit both validate the department/location group still sums to 100 after the change (409 `KPI_WEIGHT_MISMATCH` on drift).
- `PUT /departments/{id}/kpis` (optional `location_id` query param) — reconciles a department/location's *entire* KPI list in one call: an item with an `id` is updated, an item with no `id` is created, an existing KPI whose `id` is missing from the submitted list is deleted. Validated as one atomic transaction against the 100%-total rule (same `KPI_WEIGHT_MISMATCH` error, with the computed total in `message`); returns the full resulting list with real ids for newly-created KPIs, no follow-up `GET` needed. **This is the only way to delete a KPI — there is no standalone `DELETE /kpis/{id}`** (see `08_DECISIONS.md` 2026-09-29).
- `POST /kpis/{id}/scores` — record a period's actual value, server computes `score_percentage`.
- `GET /kpis/{id}/scores` — historical scores for one KPI.
- `GET /departments/{id}/performance-summary` — the quarterly rollup that feeds dashboards.
- `GET /employees/leaderboard` (filter: `department_id`, `period`) — ranked employee scores.
- `GET /company-performance-summary` (filter: `period`) — the headline dashboard section in one call.

### Task (M10+)

- `POST /tasks` — standalone/ad hoc.
- `GET /tasks` (filter: `department_id`, `assigned_to_employee_id`, `status`, `kpi_id`, `overdue=true`)
- `GET|PATCH /tasks/{id}`
- `POST /tasks/{id}/complete`

### Workflow (M11+)

- `POST|GET /workflow-templates`, `GET|PATCH /workflow-templates/{id}`
- `POST|GET /workflow-templates/{id}/steps`, `PATCH /workflow-steps/{id}`
- `POST /workflow-instances` — starts a case (body: `template_id`, `subject`)
- `GET /workflow-instances` (filter: `status`, `template_id`), `GET /workflow-instances/{id}`

### Attendance (M9+)

- `POST /attendance/clock-in`, `POST /attendance/clock-out`
- `GET /attendance` (filter: `employee_id`, date range)
