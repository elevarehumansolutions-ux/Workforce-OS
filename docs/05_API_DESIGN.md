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

**Eight modules** are mounted in `main.py` today: Identity/Memberships, Org Structure, Business DNA, OKR, Performance (KPIs), AI Suggestions, Audit Log, Notifications. Everything under "Not yet built" further down (Task, Workflow, Attendance, and Performance's own M10/M12-dependent pieces) is designed but **returns 404 today, not a stub** — check `09_PROGRESS.md` for which milestone ships each one before building against it.

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
- `POST /memberships` — add an existing user immediately, or invite an email with no account. **HR Administrator only** — not "Owner or HR Administrator": the founder is always registered *as* `hr_administrator`, so gating on that one role already covers them. Inviting someone whose membership is **deactivated** returns **409** `MEMBERSHIP_DEACTIVATED` — an invite never restores access or rewrites a role (changed 2026-10-02; it used to reactivate silently). Use `/reactivate` below.
- `POST /memberships/{id}/reactivate` — bring a deactivated teammate back; optional body `{role}` (omit to restore the role they had). **HR Administrator only.** **409** `MEMBERSHIP_NOT_DEACTIVATED` if already active; **422** if the person's employee record is offboarded (use `POST /employees/{id}/reinstate`, which restores login in the same step). Audit-logged. This is the **only** way back: `PATCH /memberships/{id}` no longer reactivates (see below).
- **Emails are case-insensitive everywhere.** Every email a client sends (register, login, resend-verification, forgot-password, invite, employee `work_email`) is trimmed and lower-cased on input, looked up in that form, and the database rejects any stored email that isn't (`CHECK (email = lower(btrim(email)))`).
- `GET /memberships` — list the org's people, offset-paginated. **HR Administrator only** — not open to every member, unlike most `GET` endpoints in this API.
- `PATCH /memberships/{id}` — change a teammate's role and/or **deactivate** them. **HR Administrator only.** A caller can't target their own membership this way, and can't deactivate the org's Owner. `is_deactivated` accepts only `true`; `false` is a **422** that points at `POST /memberships/{id}/reactivate` (changed 2026-10-02; reactivation used to work here without the offboarded-employee check or an audit entry).

`GET /ai-usage` — the org's own `ai_usage_log`, newest call first, offset-paginated. **`hr_administrator`-only** (not open to `business_executive`, unlike AI suggestion review — this is the org's own cost/usage visibility, a narrower audience). Its screen doesn't land until M13 (paired with Billing History), not overlooked.

**Not yet built:** `GET /billing/history`. Designed (see `04_DATABASE.md`) but not mounted in the code — calling it 404s. Its own backend milestone isn't scheduled yet as of this audit.

## Org Structure

Mutations (`POST`/`PATCH`/`DELETE`, including offboard/reinstate) restricted to `hr_administrator`; `GET` (list and by-id) open to any authenticated org member.

- `POST|GET /locations`, `GET|PATCH|DELETE /locations/{id}`
- `POST|GET /departments`, `GET|PATCH|DELETE /departments/{id}` — includes `is_critical`, `revenue_allocation_percentage`. `DELETE` returns **409** while active positions are still assigned, or a pending AI suggestion still targets it (the response's `message` names which reason(s) apply). `POST`/`PATCH` return **409** if the name duplicates another non-deleted department in the org (compared case/spacing/Unicode-insensitively — `"Sales"` and `"  sales "` collide). **Creating a department with `is_critical: true`, or updating one to become critical, enqueues AI suggestion generation** (see the Conventions note above).
- **Department head** (added 2026-10-06): every department response carries `head_employee_id` (null until HR names one). `PATCH /departments/{id}` accepts `head_employee_id`: a UUID sets it, `null` clears it, leaving it out keeps it. It is *not* accepted on `POST /departments`, because during onboarding no employee exists yet. The employee must be an **active employee of the same organization** (any department; one person may head several): **404** `EMPLOYEE_NOT_FOUND` for an unknown id or one from another organization, **422** `VALIDATION_FAILED` ("An offboarded employee can't head a department") for an offboarded one, **403** for a non-`hr_administrator`. Changes are audit-logged with old and new. `POST /employees/{id}/offboard` **clears the head** of every department that employee headed, writes an audit entry per department, and notifies every active HR administrator (category `system`, title "A department needs a new head", `link_type: "department"`, `link_id` set when exactly one department was affected); `POST /employees/{id}/reinstate` does **not** restore it. There is no endpoint listing the departments an employee heads.
- **Reporting hierarchy rules on positions** (added 2026-10-07): `reports_to_position_id` (on `POST` and `PATCH /positions`) names the position this one reports to; `null` clears it, and leaving it out keeps it. The parent must be a non-deleted position **of the same organization**, in any department (the CTO in Technology can report to the CEO in Executive): **404** `POSITION_NOT_FOUND` with the message "The position it should report to was not found" for an unknown id, another organization's position, or a deleted one (note this 404 is about the *parent*, the position being edited exists). **422** `VALIDATION_FAILED` for a position reporting to **itself** ("A position cannot report to itself") and for anything that would create a **loop** (A to B and B to A, or any longer ring; "That would create a reporting loop…"). Checked only when `reports_to_position_id` is sent and not null. There is no tree endpoint: build the tree from `GET /positions` (offset-paginated, `limit` up to 100, so fetch every page). This is the *position* hierarchy (the org chart of roles); a person's own manager is `employees.manager_id`.
- `POST|GET /positions`, `GET|PATCH|DELETE /positions/{id}` — `DELETE` returns **409** while active employees hold it, other positions report to it, or a pending AI suggestion still targets it. **Every `POST /positions` enqueues AI suggestion generation**, unconditionally, regardless of whether its department is critical.
- `POST|GET /employees` (filter: `location_id`), `GET|PATCH /employees/{id}` — no `DELETE`; offboarding is the removal mechanism instead.
- `POST /employees` also takes `grant_login_access` + `role` (the Add Employee checkbox; `role` required with the flag, cannot be combined with `user_id`). It creates the employee and gives them login access in one all-or-nothing call (SAVEPOINT). Passing `user_id` instead links an existing org member directly; the user must be an active member of the org (404 `USER_NOT_FOUND` otherwise, 409 `MEMBERSHIP_DEACTIVATED`) and not already linked to another employee (409 `EMPLOYEE_USER_ALREADY_LINKED`).
- `POST /employees/{id}/grant-login` (`hr_administrator`, body: `role`) — "Send invite". Uses the employee's `work_email`: an active org member with that email is linked now (`outcome: "linked"`, role unchanged); another existing account with no membership here is added with `role` and linked now (`"added"`); an existing member who is deactivated here is refused (**409** `MEMBERSHIP_DEACTIVATED`, reactivate them first); otherwise an invite carrying the employee is emailed (`"invited"`) and `POST /auth/accept-invite` links the new user to that employee. Calling it again replaces the pending invite (the old link stops working), so it is also the resend action. 409 `EMPLOYEE_ALREADY_HAS_LOGIN` if the employee already has a login; 422 if the employee is offboarded.
- `POST /employees/{id}/link-user` (`hr_administrator`, body: `user_id`) — manual link of an existing org member to an employee with no login (e.g. the founder). Same validation as above. `user_id` is one-way everywhere: no endpoint clears or swaps it (offboarding finds the login to deactivate through it), and `PATCH /employees/{id}` cannot touch it.
- **Every employee response carries `invite_status`** (added 2026-10-02): `"pending"` (a login invite sent from this employee's row is waiting and its link still works), `"expired"` (it lapsed; send it again with `grant-login`), or `null` (no invite waiting: the employee already has a login, or none was ever sent). Computed per response (one extra query per page on `GET /employees`), so it is present on create, update, offboard, reinstate, link-user and grant-login responses too.
- `GET /employees/unlinked-members` (`hr_administrator`, offset-paginated) — active org members with no employee record, for the link picker.
- `POST /employees/{id}/offboard` — sets the employee inactive and deactivates their `Membership` if they have login access, in one step. Not a generic status PATCH.
- `POST /employees/{id}/reinstate` — reverses an offboard: restores active status and re-enables login access if it was deactivated.

## Business DNA

- `GET|PUT /business-dna` — one row per org; `PUT` upserts (works for both the first save and every later edit, no separate create/update). `PUT` is `hr_administrator`-only; `GET` is open to any authenticated org member. `PUT`'s body also carries `organization_name`, written through to `organizations.name` in the same transaction, and `timezone` (added 2026-10-02), written through to `organizations.timezone`: an IANA name spelled exactly (`Africa/Lagos`, not `africa/lagos`, `WAT` or `+01:00`), else **422**; an explicit `null` is ignored (the column is `NOT NULL`). It defaults to `Africa/Lagos` and decides where "midnight" falls for the attendance auto-close. Every response from `GET`/`PUT` carries `timezone` (always a string). Note `GET /business-dna` is still a 404 until the first `PUT`, so the current timezone can't be read before then.
- **Field-level restriction, not a role gate on the whole endpoint:** `capital_investment_amount` in `GET /business-dna`'s response is `null` for every role except `hr_administrator`/`business_executive` — never a 403, the field is just empty for everyone else.
- `POST|GET /business-dna/core-values`, `PATCH|DELETE /business-dna/core-values/{id}` — mutations `hr_administrator`-only, reads open to any authenticated org member. `DELETE` is a genuine hard delete (**204, no body**) — the one place in this whole API that isn't a soft delete.

## OKR

`POST`/`PATCH` on `okrs` and `key_results` restricted to `hr_administrator`; `GET` open to any authenticated org member. No `DELETE` yet — deferred to M8.

- `POST|GET /okrs` (filter: `department_id`, `location_id`), `GET|PATCH /okrs/{id}`. **`POST /okrs` enqueues AI suggestion generation** (a new objective is prompt context for the `missing_department` suggestion type); editing an existing OKR does not.
- `POST|GET /okrs/{id}/key-results`, `PATCH /key-results/{id}` — same role gate and pagination envelope as the parent resource.

## Performance

Single-KPI `POST`/`PATCH` and the group reconcile are `hr_administrator`-only; `GET` open to any authenticated org member (an Employee in one department can read another department's KPIs, same precedent as OKRs/Business DNA). The scores upsert is the one exception — `hr_administrator` **or** `business_executive`, matching AI suggestion review (08_DECISIONS.md 2026-09-29/30).

- `POST|GET /kpis` (filter: `department_id`, `location_id`), `GET|PATCH /kpis/{id}` — single-KPI create/read/edit; create and edit both validate the department/location group still sums to **at most** 100 after the change (409 `KPI_WEIGHT_MISMATCH` on drift, with the computed total in `message`). `is_inverse` (lower-is-better, e.g. "customer complaints") and `tracking_mode` (`manual`/`task_count`) are both set here. **`tracking_mode` is accepted on `POST /kpis` (optional, defaults to `manual`) and on `PATCH /kpis/{id}` (optional; leaving it out keeps the current mode; sending `null` is a 422) since 2026-10-09 (M10 slice F).** A `task_count` KPI's live progress is read from `GET /kpis/{id}/task-progress` (Task section). The group `PUT /departments/{id}/kpis` does not carry `tracking_mode` (a KPI created through it is `manual`; editing through it leaves the mode alone). **Since 2026-10-09, `PATCH /kpis/{id}` answers an explicit `null` on `name`, `weight`, `is_inverse` or `tracking_mode` with a clean 422** (leaving a field out still means "keep it"; `description`, `target_value`, `unit` and `key_result_id` can still be cleared with `null`). Before, those were unhandled 500s. **`POST /kpis` enqueues `kpi_weight` AI suggestion generation**, unconditionally, same pattern as positions.
- `PUT /departments/{id}/kpis` (optional `location_id` query param) — reconciles a department/location's *entire* KPI list in one call: an item with an `id` is updated, an item with no `id` is created, an existing KPI whose `id` is missing from the submitted list is deleted. Validated as one atomic transaction against the **exactly** 100%-total rule (same `KPI_WEIGHT_MISMATCH` error); returns the full resulting list with real ids for newly-created KPIs, no follow-up `GET` needed. **This is the only way to delete a KPI — there is no standalone `DELETE /kpis/{id}`** (08_DECISIONS.md 2026-09-29). Also enqueues `kpi_weight` generation.
- `POST /kpis/{id}/scores` — for a `manual`-tracking KPI (a `task_count` KPI is refused with **409 `KPI_TRACKED_BY_TASKS`**, since 2026-10-09: its number comes from completed tasks, so a typed-in value would contradict it): upsert the *current, still-open* period's actual value; server recalculates `score_percentage` on every call, honoring `is_inverse`. Repeatable while the quarter is running (so progress is visible mid-quarter, not just at close); 409 `KPI_SCORE_PERIOD_CLOSED` once `period_end` has passed — a correction after that point is a new period's row (08_DECISIONS.md 2026-09-29).
- `GET /kpis/{id}/scores` — historical scores for one KPI, newest period first.

**Live progress read: BUILT 2026-10-09** (M10 slice F): `GET /kpis/{kpi_id}/task-progress`, documented under "Task (M10)" below (it is served by the Task module). **Still not built (M12):** the scheduled job that closes a `task_count` KPI out at quarter-end (same shape as the Quarterly Objective Review). **Gap found and closed 2026-10-09:** the KPI create and update endpoints could not set `tracking_mode`; `KPICreate` and `KPIUpdate` now accept it (the user's permission, 2 schema lines). (08_DECISIONS.md 2026-09-30 and 2026-10-09.)

## AI Suggestions

- `GET /ai-suggestions` (filter: `status`, `suggestion_type`; `page`/`limit` offset pagination, newest first) — **HR Administrator or Business Executive.** Review actions below are open to the **same two roles**.
- `POST /ai-suggestions/{id}/approve` — **no body.** Approves exactly as the AI proposed (`status → approved`) and applies it to the real position/department/KPI. For `kpi_weight`, this reuses `PATCH /kpis/{id}`'s own weight-sum validation — a proposal that would push its group over 100% is rejected (409) and the suggestion stays pending, same as every other write-through failure.
- `POST /ai-suggestions/{id}/edit` — body: only the fields the reviewer is *changing* (`criticality_type`, `risk_level` for a `critical_position`; `revenue_allocation_percentage` for a `revenue_allocation`; `department_name` for a `missing_department`; `weight` for a `kpi_weight`); anything left out keeps the AI's own value. `status → edited`, then applied. **422** if a field doesn't apply to the suggestion's type, if the body is empty, or if every supplied value equals the AI's own (that's an approve — call `/approve` instead). **The frontend must diff the form and send only the fields that actually changed** — resending the whole form as "the edit" will 422 whenever the reviewer didn't change anything.
- `POST /ai-suggestions/{id}/reject` — no body. Starts a quarterly suppression, so the same suggestion isn't proposed again this fiscal quarter. **404** if not visible to the caller's org; **409** if already reviewed (applies to approve/edit/reject alike — a second reviewer clicking the same button gets 409, not a silent overwrite).

**Decision rule for the frontend, worth building into the UI directly:** if nothing on the form changed from the AI's proposal, call `/approve`. If anything changed, call `/edit` with only the changed fields. Don't always call `/edit` "to be safe" — an edit with nothing changed 422s by design.

## Blueprint (AI-proposed set-up; added 2026-10-22)

After a company FIRST saves its Business DNA, the AI proposes its departments, positions (with who each reports to: the organogram), objectives with key results, and renames of anything it already has. Nothing is real until HR approves. All endpoints: **HR Administrator or Business Executive** (`generate`: HR Administrator only). Why and how: `08_DECISIONS.md` 2026-10-22.

- `GET /blueprint` (filters `status` = pending/approved/edited/rejected, `kind`; `page`/`limit`, default limit 100, max 100) — the items, newest batch first, in the AI's own order. Item fields: `id`, `kind` (`department`, `position`, `objective`, `key_result`, `kpi`, `rename_department`, `rename_position`, `review_note`), `ref`, `title` (the name/title/text; for a rename, the NEW name; for a note, its heading), `rationale`, `status`, `reviewed_title`, `created_entity_id` (the real row once approved), and how it hangs together: a position has `department_ref` (the `ref` of a proposed department) OR `department_id` (an existing one), and `reports_to_ref` OR `reports_to_position_id` (blank = top of the chart); an objective has `department_ref`/`department_id` (both blank = company-wide); a key result has `objective_ref`. A **`kpi`** (added 2026-10-22) has `title` (its name), `rationale`, its department (`department_ref` or `department_id`, always set), and `key_result_ref` (the key result it measures, or null), `kpi_weight` (percent of that department's KPIs; a department's proposed KPIs add up to the room it has, 100 for a new one; **decimals arrive as strings**, e.g. `"60.00"`), `kpi_target_value` (nullable), `kpi_unit` (nullable) and `kpi_is_inverse` (true = a LOWER figure is better). Approving a KPI creates a real KPI (tracking mode `manual`) after its department and, if it has one, its key result and objective; it can be refused with `409` "KPI weights for this department must not exceed 100%" if HR added KPIs by hand in the meantime (accept-all skips it with that reason). Rename and note items carry `department_id` or `position_id` of the existing row. Build the tree on screen from `ref`s.
- `POST /blueprint/generate` — no body. Always **202**: `{"status": "queued"}` (runs in the background; poll `GET /blueprint?status=pending`, and there is a notification, `link_type` `"blueprint"`), or `{"status": "already_pending"}` when items still wait for review (nothing queued).
- `POST /blueprint/accept-all` — no body. Approves every pending item, parents first. `{"accepted": N, "skipped": [{"id", "title", "reason"}]}`; a skipped item stays pending (for example a rename that clashes with an existing department name).
- `POST /blueprint/{id}/approve` — no body. Creates the real department/position/OKR/key result (or applies the rename). **Its pending parents are approved first** (approving a position also creates its department and boss). Returns the item.
- `POST /blueprint/{id}/edit` — body `{"title": "..."}` (1 to 300 characters; 422 otherwise). Same as approve with HR's own wording (`status` `edited`). Only the wording can be edited.
- `POST /blueprint/{id}/reject` — no body.
- **Errors:** `404 BLUEPRINT_ITEM_NOT_FOUND` (also another organization's item); `409 BLUEPRINT_ITEM_ALREADY_REVIEWED`; `409 BLUEPRINT_PARENT_REJECTED` (the item depends on a rejected department or objective; message names it); plus whatever the real create can say, for example `409` "A department named 'X' already exists" on a rename that clashes.
- **Not provided:** merging duplicates (the AI flags them with a `review_note`; approving a note only marks it seen), deleting anything the company already has, proposing changes to existing reporting lines. A rejected BOSS is not an error: the position is simply created at the top of the chart.
- **Trigger:** `PUT /business-dna` enqueues generation only the first time. Later DNA edits do nothing; use `POST /blueprint/generate`.

## Audit Log

- `GET /audit-log` (filter: `entity_type`, `entity_id`, `actor_user_id`, `date_from`, `date_to`; `cursor`/`limit`, cursor-paginated) — **HR Administrator or Business Executive only**, not open to every member. No dedicated viewer screen required for MVP, but reachable via API for support/debugging use.

## Notifications

- `GET /notifications` (filter: `category`, `unread=true`) — the caller's own stream, self-scoped by recipient, open to every role.
- `POST /notifications/{id}/read` — mark one of the caller's own notifications read.
- `POST /notifications/read-all` — mark every one of the caller's unread notifications read in one call; returns `{"marked_read": <count>}`.

---

## Attendance

Plain clock-in/clock-out. **Attendance belongs to the employee record, not the role:** any authenticated member who also has an employee record can clock in and out. Matched through `employees.user_id`; no employee record means **409 `NO_EMPLOYEE_PROFILE`** on every endpoint below (e.g. a founder until HR adds them as an employee).

- `POST /attendance/clock-in` — no body. Response `{already_clocked_in, record}`. **Idempotent:** clocking in while already clocked in is not an error — it returns the existing open record with `already_clocked_in: true` (a double-tap, or two devices at once; the database guarantees one open record per employee). 422 if the employee has been offboarded.
- `POST /attendance/clock-out` — no body. Returns the closed record (`closed_by: "employee"`). **Not idempotent:** **409 `NOT_CLOCKED_IN`** if there is no open record (including a second tap on Clock Out — the first clock-out time stands).
- `GET /attendance` — offset-paginated, newest clock-in first. Filters: `employee_id`, `date_from`, `date_to` (calendar days, inclusive, `YYYY-MM-DD`). **Dates are days on the organization's wall clock — its `timezone` — not UTC**, so a 00:30 Lagos clock-in belongs to that Lagos day. `date_from` after `date_to` is **422**.
  - No `employee_id` = the caller's own history. `hr_administrator` and `business_executive` may pass any employee of their organization; every other role asking for someone else gets **403**; an unknown employee, or one in another organization, is **404**.
  - There is no separate "am I clocked in?" endpoint: the caller's newest record with `clock_out_at: null` means they are clocked in right now (`GET /attendance?limit=1`).
- **Record shape:** `id, organization_id, employee_id, clock_in_at, clock_out_at (null = clocked in), closed_by ("employee" | "system" | null), close_reason, created_at, updated_at`. `closed_by: "system"` marks a record the **nightly auto-close** ended: an hourly Beat job closes every record that clocked in before the organization's most recent midnight (its own `timezone`), setting `clock_out_at` to that midnight, `close_reason: "Did not clock out"`. That time is a cutoff, not something the employee did, so show these rows differently. The employee and their manager (if they have logins) each get an in-app notification (category `system`, `link_type: "attendance_record"`, `link_id` = the record); no email. No endpoint: it is a background job.
- Clock-in and clock-out each write an `audit_log` entry (`entity_type: attendance_record`); a repeat clock-in writes none.

## Not yet built — designed, not mounted in the code

Nothing below this line exists as a real endpoint today — every path here 404s. These sections describe the intended shape for whichever milestone eventually builds them; check `09_PROGRESS.md` before writing frontend code against any of them, and don't scaffold API client code for these yet, since the shape may still change before it's actually built.

### Performance (M12, dashboards)

- `GET /departments/{id}/performance-summary` — the quarterly rollup that feeds dashboards.
- `GET /employees/leaderboard` (filter: `department_id`, `period`) — ranked employee scores.
- `GET /company-performance-summary` (filter: `period`) — the headline dashboard section in one call.

### Task (M10)

**Built (slice A, 2026-10-07):**

- `POST /tasks` — body `{department_id, title, description?, due_at?, kpi_id?, assigned_to_employee_id?}`. `due_at` must carry a timezone. Allowed to an HR administrator, the `manager` role, or the head of `department_id`. `department_id` is the department *doing the work*. A creator from another department cannot pick the individual (422 `VALIDATION_FAILED`); the task is assigned to that department's head, or stays unassigned (`assigned_to_employee_id: null`) with the HR administrators notified if it has none. A plain employee gets 403 `PERMISSION_DENIED`. 404 `DEPARTMENT_NOT_FOUND` / `EMPLOYEE_NOT_FOUND` / `KPI_NOT_FOUND`; 422 for an offboarded assignee, empty title, or a `due_at` with no timezone. The assignee (or the head, for a cross-department task) gets an in-app notification "New task: <title>".
- `GET /tasks` — paginated (`page`, `limit`, `{data, pagination}`), newest first. Filters: `department_id`, `assigned_to_employee_id`, `status` (`open`/`in_progress`/`completed`/`cancelled`), `kpi_id`. HR administrators and business executives see all; everyone else sees tasks assigned to them, created by them, or belonging to a department they head (the `manager` role also sees its own department).
- `GET /tasks/{id}` — 404 `TASK_NOT_FOUND` both when it doesn't exist and when it is outside the caller's view.
- `PATCH /tasks/{id}` — `title`, `description`, `due_at`, `kpi_id` only; any other field (including `status`, `assigned_to_employee_id`, `department_id`) is rejected with 422. At least one field required. Allowed to HR, the department head and the creator; the assignee gets 403. 409 `TASK_NOT_OPEN` if the task is completed or cancelled. Changing `due_at` is audit-logged with old and new values.
- `POST /tasks/{id}/complete` — allowed to the assignee, the department head and HR (403 for anyone else who can see it). Not idempotent: a second call is 409 `TASK_NOT_OPEN` and the first `completed_at` stands.

**Built (slice B, 2026-10-08):**

- `POST /tasks/{id}/cancel` — body `{reason}` (required, trimmed, 1-500 chars; unknown fields rejected). Allowed to HR, the department head and the task's creator, **not the assignee** (403 `PERMISSION_DENIED`). Returns the task with `status: "cancelled"` and `cancel_reason`. Final: a cancelled task can't be cancelled again, completed, edited or reassigned (all 409 `TASK_NOT_OPEN`), and a completed task can't be cancelled (409 `TASK_NOT_OPEN`). The assignee is notified "Task cancelled: <title>" (unless they cancelled it themselves).
- `POST /tasks/{id}/reassign` — body `{assigned_to_employee_id, due_at}`, **both required** every time; `due_at` must carry a timezone and be in the future. Also the way to assign an unassigned task. Allowed to HR, the department head, and the creator only if they work in the task's department (otherwise 403). Returns the task with the new assignee and deadline and `status: "open"`. Errors: 422 `VALIDATION_FAILED` (deadline in the past / without timezone / missing, the person already has the task, the person is offboarded), 404 `EMPLOYEE_NOT_FOUND`, 409 `TASK_NOT_OPEN` (closed), 409 `TASK_CHANGED` (someone else reassigned it at the same moment: reload the task and retry). The new assignee gets "New task: <title>", the previous one "Task reassigned: <title>".

**Built (slice C part 1, 2026-10-08): the clock-in gate.** An employee sees and works on tasks *assigned to them* only while clocked in (`01_REQUIREMENTS.md`: the list is "never shown before clock-in"). Every refusal is **409 `NOT_CLOCKED_IN`**, message "Clock in to see and work on your tasks." (the same code `POST /attendance/clock-out` uses, with its own message).
- `GET /tasks?assigned_to_employee_id=<caller's own employee id>` while not clocked in -> 409. This is the "My tasks" call.
- `GET /tasks/{id}` and every single-task action (`complete`, edit, `cancel`, `reassign`) on a task whose only link to the caller is "assigned to me", while not clocked in -> 409. A caller who cannot see the task at all still gets 404.
- `GET /tasks` with **no** filter while not clocked in -> 200 with the caller's assigned-to-me tasks left out (not an error, so it is not a reliable "my tasks").
- **Not gated:** what a caller sees as creator, department head, `manager` role, HR administrator or executive. Callers with no employee record are unaffected.
- "Clocked in" = an open attendance record (`AttendanceRepository.get_open_record`). A forgotten clock-out from yesterday counts as clocked in until the hourly auto-close job runs (up to about an hour past the organization's midnight); accepted, the gate is a nudge, not security.

**Built (slice C part 2, 2026-10-08): derived "overdue".** Every task response now carries `overdue: bool`, and `GET /tasks` accepts `?overdue=true` (only overdue tasks), `?overdue=false` (only tasks that are not overdue), or neither (all). Nothing is stored. A task is overdue when it has a `due_at`, `due_at` is strictly before now, and its status is `open` or `in_progress`. No deadline, completed and cancelled tasks are never overdue; a task due exactly now is not overdue yet. The filter and the flag use the same instant for one request. Both forms of the rule live in `tasks/overdue.py`; a test checks they agree. **Updated by slice E:** a task that is blocked right now is never overdue, and the "real deadline" is `due_at` plus the task's `approved_blocked_seconds` (see slice E below). `due_at` itself never changes.

**Built (slice D, 2026-10-08): overdue notifications** (no endpoint; a background job). Every 10 minutes the server announces tasks that have become overdue, once each, as an in-app notification (`GET /notifications`): `category: "task"`, `title: "Task overdue: <task title>"`, `link_type: "task"`, `link_id` = the task id (the screen should open that task). Recipients: the assignee (if active), plus the department head; with no head, the HR administrators. If the deadline is later changed (`PATCH` with `due_at`) or the task is reassigned, it can be announced again when it becomes overdue again. No email.

**Built (slice E, 2026-10-09): blocking tasks and the review.** A block says "this task can't move forward because of something outside the assignee's hands". While a task is blocked it is never overdue. A reviewer then approves or rejects the block; only an **approved** block gives the blocked time back, by pushing the task's real deadline later (`due_at` + `approved_blocked_seconds`). `due_at` is never changed.
- `POST /tasks/{id}/block` `{category, reason}`. `category`: `awaiting_approval` | `awaiting_other_department` | `external_dependency` | `other`; `reason` 1-500 characters (trimmed, unknown fields rejected). **Only the assignee** (403 `PERMISSION_DENIED` for everyone else, including the head and HR). Returns the new block with `review_status: "pending"`. Errors: 409 `TASK_ALREADY_BLOCKED` (one open block per task), 409 `TASK_NOT_OPEN` (completed/cancelled), 409 `TASK_CHANGED` (race), 409 `NOT_CLOCKED_IN` (the clock-in gate), 404 `TASK_NOT_FOUND`, 422. Allowed after the deadline too: `blocked_at` is always the moment it is recorded, never backdated.
- `POST /tasks/{id}/unblock` (no body). The assignee, the department head or HR. Returns the block with `unblocked_at` set. 409 `TASK_NOT_BLOCKED` if the task isn't blocked.
- `GET /tasks/{id}/blocks`: every block the task has had, newest first (plain list).
- **Block fields:** `id, organization_id, task_id, blocked_by_user_id, category, reason, blocked_at, unblocked_at (null = still blocked), review_status (pending|approved|rejected), reviewed_by_user_id, reviewed_at, created_at, updated_at`.
- `GET /task-blocks?review_status=pending|approved|rejected&page&limit`: a **reviewer's to-do list** (default `pending`), paginated, newest first. Rows are the block fields plus `task_title`, `task_department_id`, `task_due_at` (a reviewer such as a reporting manager may not be allowed to open the task). A caller sees a block only if they are an HR administrator, the head of the task's department, or the blocker's own reporting manager (`employees.manager_id`); **never their own blocks**.
- `POST /task-blocks/{id}/approve` and `/reject` (no body). Same people as above. Returns the block. 404 `TASK_BLOCK_NOT_FOUND` (does not exist **or** you may not review it, deliberately the same), 409 `TASK_BLOCK_ALREADY_REVIEWED`. Approving a block that has already ended adds its length to the task's `approved_blocked_seconds` immediately; approving one still open adds it when the task is unblocked. Rejecting adds nothing.
- **Cancel, reassign and complete all end an open block** (its `unblocked_at` is set; the review status is left as it was, so a reviewer can still judge it). **Reassign also resets** `blocked_since` and `approved_blocked_seconds` to empty/0, so the new assignee starts clean.
- **Notifications:** a new block notifies who should review it: the blocker's reporting manager if set, else the department head, else the HR administrators (never the blocker): `category: "task"`, title `Task blocked: <task title>`, `link_type: "task_block"`, `link_id` = the block id. After a review the blocker gets `Block approved: <title>` / `Block rejected: <title>` (`link_type: "task"`). When an overdue task has **never had a block**, the assignee also gets the invitation `Was something holding up: <title>?` (`link_type: "task"`) explaining they can mark it blocked.
- **Task responses now also carry** `blocked_since` (null unless blocked right now) and `approved_blocked_seconds` (total approved blocked time).

`TaskResponse`: `id, organization_id, workflow_instance_id, workflow_step_id, department_id, kpi_id, assigned_to_employee_id, title, description, due_at, completed_at, cancel_reason, status, overdue, blocked_since, approved_blocked_seconds, created_by_user_id, deleted_at, created_at, updated_at`.

**Built (2026-10-09): handover when someone is offboarded** (no endpoint; the same 10-minute background job). Open tasks (`open`/`in_progress`) assigned to an offboarded employee become **unassigned** (`assigned_to_employee_id: null`, status unchanged), any open block on them is ended, and the department head (or the HR administrators if there is no head) gets one in-app notification per person who left: `category: "task"`, title `<First Last> left: <N> task(s) need a new owner`, `link_type: "department"`, `link_id` = the department id. The head then reassigns each with `POST /tasks/{id}/reassign` (new deadline required). Completed and cancelled tasks keep the person's name. It can take up to about 10 minutes after the offboarding. Reinstating the employee does not give the tasks back. **Consequence for screens:** an open task can become unassigned *after* creation, so every task view must handle `assigned_to_employee_id: null` (show an "Assign" action).

**Built (slice F, 2026-10-09): live progress of a task-count KPI.** `GET /kpis/{kpi_id}/task-progress` (any member of the organization, like reading the KPI itself). Counts the tasks linked to the KPI (`tasks.kpi_id`) that were **completed** within the organization's **current fiscal quarter** (from `fiscal_year_start_month`, measured on the organization's own clock/timezone); open, blocked and cancelled tasks do not count, and it is a total for the KPI, not limited to what the caller can see. Nothing is stored. Response: `{kpi_id, period_start, period_end (the quarter's last day, inclusive), completed_tasks, target_value, unit, score_percentage}`. `score_percentage` uses the KPI module's own rule (`completed_tasks / target_value * 100`, inverted for `is_inverse`), so it is `null` when there is no target or a zero divisor. Errors: 404 `KPI_NOT_FOUND`; 422 `VALIDATION_FAILED` ("This KPI is tracked by typed-in values, not by counting tasks") for a `manual` KPI. A KPI becomes task-count via `tracking_mode` on `POST /kpis` or `PATCH /kpis/{id}` (see the KPI section).

**Not built yet:** any way to set `in_progress` (deferred, a small later endpoint).

### Workflow (M11)

**Templates and steps: BUILT 2026-10-12 (slice B).** Instances (start, list, read, cancel) are not built yet (slices C to E). Design: `08_DECISIONS.md` 2026-10-12.

**Who:** building (every create, edit, archive, delete, add/edit/delete step, reorder) is `hr_administrator` or `manager` (any manager may edit any template); anyone else gets 403 `PERMISSION_DENIED`. Reads are open to every member of the organization. Anything outside the caller's organization is a 404.

`TemplateResponse`: `id, organization_id, department_id, name, created_by_user_id, archived_at, created_at, updated_at`.
`StepResponse`: `id, organization_id, workflow_template_id, step_order, name, department_id, default_assignee_employee_id, default_turnaround_hours, created_at, updated_at`.

| Endpoint | What it does |
|---|---|
| `POST /workflow-templates` | body `{name (1-200 chars, trimmed), department_id}`; 404 `DEPARTMENT_NOT_FOUND` |
| `GET /workflow-templates` | query `include_archived` (default false), `department_id`, `page`, `limit`; sorted by name; paginated envelope |
| `GET /workflow-templates/{id}` | works for archived templates; 404 `WORKFLOW_TEMPLATE_NOT_FOUND` |
| `PATCH /workflow-templates/{id}` | send only `name` and/or `department_id`; `null` on either is a 422 |
| `POST /workflow-templates/{id}/archive` | retires it (cannot start new cases; running ones carry on); 409 `WORKFLOW_TEMPLATE_ALREADY_ARCHIVED` |
| `POST /workflow-templates/{id}/unarchive` | 409 `WORKFLOW_TEMPLATE_NOT_ARCHIVED` if it is not archived |
| `DELETE /workflow-templates/{id}` | soft delete; 409 `RESOURCE_IN_USE` ("N case(s) are still running on it. Archive it instead") while any case is `in_progress` |
| `POST /workflow-templates/{id}/steps` | body `{name, department_id, default_assignee_employee_id?, default_turnaround_hours? (>0), step_order? (>=1)}`; no `step_order` = at the end, a number inserts there and moves later steps down; 422 if the position is beyond one past the last step, or the assignee is offboarded; 404 `EMPLOYEE_NOT_FOUND` / `DEPARTMENT_NOT_FOUND` |
| `GET /workflow-templates/{id}/steps` | plain list (not paginated), in order; works for archived templates |
| `PATCH /workflow-steps/{id}` | send only the fields to change; `null` on `default_assignee_employee_id` / `default_turnaround_hours` clears them; `null` on `name` / `department_id` is a 422; the position is not editable here; 404 `WORKFLOW_STEP_NOT_FOUND` |
| `DELETE /workflow-steps/{id}` | soft delete, later steps move up; 409 `RESOURCE_IN_USE` ("N task(s) are still open on it") while a task made from it is open or in progress |
| `PUT /workflow-templates/{id}/steps/order` | body `{step_ids: [...]}` = every step id of the template in the new order; 422 if the list is not exactly the template's steps; 409 `RESOURCE_IN_USE` ("N case(s) are still running on this template") while any case is in progress; returns the steps in the new order |

**Cases (instances): start, list, read: BUILT 2026-10-12 (slice C).** Cancelling a case and the automatic next-step tasks are not built yet (slices D and E).

`InstanceResponse`: `id, organization_id, workflow_template_id, subject, started_by_user_id, status (in_progress | completed | cancelled), started_at, completed_at, cancel_reason, created_at, updated_at`.
`InstanceDetailResponse` = `InstanceResponse` + `steps` (the template's CURRENT steps, as `StepResponse`, in order) + `tasks` (the tasks the case has created so far, oldest first: `id, workflow_step_id, department_id, assigned_to_employee_id, title, status, due_at, completed_at, cancel_reason, created_at`; match a task to its step by `workflow_step_id`; use `GET /tasks/{id}` for the full task with the overdue flag).

| Endpoint | What it does |
|---|---|
| `POST /workflow-instances` | body `{template_id, subject (1-200 chars, trimmed)}`; starts a case and creates ONLY step 1's task at once. WHO: any active employee, or an HR administrator (who may have no employee record); anyone else 403 `PERMISSION_DENIED` "Only employees can start a workflow". 404 `WORKFLOW_TEMPLATE_NOT_FOUND` (also a deleted or other-company template), 409 `WORKFLOW_TEMPLATE_ARCHIVED`, 422 "This template has no steps yet..." |
| `GET /workflow-instances` | query `status`, `template_id`, `page`, `limit` (1-100); newest first; paginated envelope; only the cases the caller may see (below) |
| `GET /workflow-instances/{id}` | the detail above; 404 `WORKFLOW_INSTANCE_NOT_FOUND` also means "exists but you may not see it" |

**Who sees a case:** HR administrators and business executives see every case. Everyone else sees a case if they STARTED it, have (or had) a TASK in it (assigned to their employee record, even a completed one), or are the named HEAD of a department that has a step in its template (so a head sees a case before their step's task exists). Not gated by clock-in. Anything else is a 404 and absent from the list. The `manager` role alone does not grant visibility.

**The first task:** title `"<step name>: <subject>"` (cut to 255 characters), description `Step 1 of N in "<template name>" for <subject>.`, department = the step's, assignee = the step's default assignee, `created_by_user_id` null (no human creator), `workflow_instance_id` / `workflow_step_id` set. Deadline = now plus the step's turnaround in BUSINESS HOURS (Monday to Friday 09:00 to 17:00 in the organization's timezone; public holidays are not skipped); no turnaround means `due_at` null. If the default assignee is missing or offboarded, or the step has none, the task is created UNASSIGNED and the department head (the HR administrators if there is no head) is notified "A task for <department> needs an owner" (category task, link to the task); otherwise the assignee is notified "New task: <title>".

**The chain: BUILT 2026-10-13 (slice D).** Nothing to call: it happens when a task of a case is completed or cancelled (`POST /tasks/{id}/complete`, `POST /tasks/{id}/cancel`). The case reads "what comes next" from the template AS IT IS NOW (steps added, removed or edited since the case started are respected) and:
- **after a completion:** creates the next step's task (deadline = the moment of completion plus the step's turnaround in business hours, none if the step has no turnaround; same assignee / unassigned rules as the first task). After the LAST step the case becomes `completed` (`completed_at` set).
- **after a cancel by hand (a "skip"):** the same, as if the step had been done. The case's starter is told (not when they cancelled it themselves): notification category `task`, title `"A step was skipped on <subject>"`, body `"<step>" was skipped by <name>: <reason>. The case moved on to "<next step>".` (or `That was the last step, so the case is now complete.`), `link_type` **`"workflow_instance"`** and `link_id` = the case id (a new link type the Notifications screen must handle). The skip is audit-logged on the case (`skip_step`).
- **a case that is no longer `in_progress`** (cancelled, or already completed) creates nothing.
- **if the next task cannot be made** (for example the next step's department was deleted), the completion or cancel itself FAILS with that error (404 `DEPARTMENT_NOT_FOUND`) and nothing is saved: the user's task stays open. A step with an open task cannot be deleted, so a step vanishing under a running task is not expected; if it happens the call is a 422 asking HR to check the workflow.

**Cancelling a case: BUILT 2026-10-13 (slice E).**

| Endpoint | What it does |
|---|---|
| `POST /workflow-instances/{id}/cancel` | body `{reason (required, trimmed, 1-500 chars)}` -> the case with `status: "cancelled"` and `cancel_reason`. WHO: an HR administrator, or the person who STARTED the case; a department head or the task's assignee gets 403 `PERMISSION_DENIED` ("Only an HR administrator or the person who started the case can cancel it"). 404 `WORKFLOW_INSTANCE_NOT_FOUND` (not visible to the caller), 409 `WORKFLOW_INSTANCE_NOT_IN_PROGRESS` (already completed or cancelled), 422 (missing/blank/too-long reason). |

Cancelling closes the case's open task automatically (cancelled with the same reason, any open block on it ended, the assignee gets the usual "Task cancelled: <title>" notification saying the workflow was cancelled and why) and no later step is ever created. The starter is NOT sent a "step skipped" notification for this. Tasks already completed stay completed. A closed task is final (completing it afterwards is 409 `TASK_NOT_OPEN`).

### Attendance — now live

Moved up to the `## Attendance` section above. Everything in M9 is built, including the nightly auto-close job (it has no endpoint).
