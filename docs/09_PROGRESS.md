# Progress

MVP milestone breakdown, dependency-ordered, no invented time estimates. Design and requirements are locked (`00`–`08`, no open scope conflicts as of 2026-09-07). Each milestone pairs its backend API surface with the frontend screens it unblocks, so Emmanuel and Uche can build side by side, matching the pairing already reflected on the Trello board.

**Explicitly excluded from every milestone below** (`01_REQUIREMENTS.md` "Explicitly Out of MVP Scope", `08_DECISIONS.md` 2026-09-03/04): Payroll (both layers) and Leave Management. Both are Phase 2. Leave Management's Phase-2 move is still unconfirmed with Jennifer, a product conversation, not a build-order question, and doesn't block this plan.

Ordering rule: a milestone is sequenced after every module it depends on per `02_SYSTEM_DESIGN.md`'s dependency graph, and infrastructure (Notifications, Audit Log, RLS/tenant context) lands before the first domain module that needs to call into it, not retrofitted later.

## Milestones

### M1 — Foundation & Infrastructure Scaffolding — ✅ DONE (2026-09-10)
Reviewed against `03_ARCHITECTURE.md`/`07_SECURITY.md`, no gaps found. See `08_DECISIONS.md` 2026-09-10. Repo initialized, committed (`439a9d2`).
**Backend:** Repo/module skeleton (`module_name/{models,repository,service,router}.py` per `02_SYSTEM_DESIGN.md`). Docker: one Dockerfile, three containers (`uvicorn`, `celery worker`, `celery beat`) per `03_ARCHITECTURE.md`. Postgres + Alembic. Redis. Celery wiring. FastAPI app entrypoint, router aggregation. CORS middleware (allow-list, `allow_credentials=True`). Base env config (`.env`, `.env.example`). The RLS regression test suite (`tests/security/test_row_level_security.py`, `test_row_level_security_behavior.py`) — written ahead of the schema it verifies, goes green as each milestone's tables land. **The `platform_admin` Postgres role** (`BYPASSRLS`, `07_SECURITY.md`) is also created here, alongside RLS itself — separate credential from the main app's `.env`, usable only from `scripts/admin/`, never the web/worker/beat containers. Provisioned this early because it's pure infra/security setup with no Billing-specific logic, and M3's Audit Log needs a real admin-script invocation path to log against.
**Frontend:** Vite/React app scaffold, API client, env config — parallel track, no shared blocker with backend yet.
**Depends on:** nothing.

### M2 — Identity, Auth & Multi-Tenancy
**Backend:** `organizations` (incl. `fiscal_year_start_month`, `DEFAULT 1` — the Quarterly Objective Review's scheduled trigger in M7 reads this, see that milestone's resolved note), `users`, `memberships` (`04_DATABASE.md` Cluster 1) + RLS policies + the `SET LOCAL app.current_org_id` tenant-context FastAPI dependency (`03_ARCHITECTURE.md`). `POST /auth/register|login|refresh|logout`, `GET /me`, `POST/PATCH/GET /memberships`. Password hashing (bcrypt/argon2). JWT with baked-in `organization_id`/`role`, short-lived access + refresh token, refresh re-validates live membership.
**Frontend:** Registration (identity-only: name, work email, password), Login, token storage (access in `localStorage`, refresh as `httpOnly` cookie), org-switcher (for multi-membership `GET /me`), Invite Teammate screen (one-time onboarding action), and separately, the **Team Management screen** — ongoing view/manage of the org's people (`GET /memberships`, role change or deactivation via `PATCH /memberships/{id}`), a distinct, later-accessed screen from the onboarding invite flow.
**Depends on:** M1.

### M3 — Audit Log & Notifications (infrastructure modules)
**Backend:** `audit_log`, `notifications` tables (`04_DATABASE.md` Clusters 8–9). Internal `log_action()` / `notify()` services — the ones every later domain module calls into. `GET /audit-log` (no viewer UI required), `GET /notifications`, `POST /notifications/{id}/read`.
**Frontend:** Notification bell/center (role-filtered stream, category filter, mark-read). No audit log viewer screen (explicitly deferred, `07_SECURITY.md`).
**Depends on:** M2 (needs `actor_user_id`/`recipient_user_id`). Built now, ahead of the domain modules that call it, per the 2026-09-06 decision that uninstrumented write paths can't be retrofitted.

### M4 — Org Structure
**Backend:** `locations`, `departments`, `positions`, `employees` (`04_DATABASE.md` Cluster 2). CRUD endpoints, `is_critical` toggle on departments, `reports_to_position_id` vs `employees.manager_id`, location filter + index, delete-blocked-while-referenced rule (named reason), audit-log calls on every mutation.
**Frontend:** Org setup screens — Departments (with Critical toggle), Positions/job architecture, Locations, Employee Directory + Add Employee (grant-login-access checkbox, Reporting Manager field, location filter).
**Depends on:** M2, M3.

### M5 — Business DNA
**Backend:** `business_dna`, `business_dna_core_values` (`04_DATABASE.md` Cluster 3). `GET|PUT /business-dna` (upsert), `POST|GET|PATCH|DELETE /business-dna/core-values`.
**Frontend:** Business DNA onboarding step (vision, mission, industry, capital investment, core values, etc. — company name captured here, not at registration).
**Depends on:** M2, M3.

### M6 — OKR
**Backend:** `okrs`, `key_results` (Cluster 4). CRUD, `department_id`/`location_id` scoping (null = corporate/dept-wide).
**Frontend:** OKR setup — corporate + departmental objectives/key results.
**Depends on:** M4 (department_id).

### M7 — AI Suggestions Engine (critical_position, revenue_allocation, missing_department)
**Backend:** `ai_suggestions`, `ai_usage_log` (Cluster 4). Shared internal LLM-calling utility (Claude, per `06_AI_DESIGN.md`), event-triggered Celery task fired from Org Structure/OKR services. Redis debounce (`NX EX 60`). Idempotent generation (partial unique index + `ON CONFLICT DO NOTHING`). ID-hallucination validation against real rows. `GET /ai-suggestions`, `POST /ai-suggestions/{id}/approve|reject`.
**Frontend:** AI Suggestions review screen — Approve/Edit/Reject for critical positions, revenue allocation (with running-total display), missing-department ("Add Department" action).
**Also here: the scheduled half of the "recurring, not one-time" requirement.** Event-triggered re-runs (a department marked critical, a new OKR saved) aren't the only trigger. The **Quarterly Objective Review** (`01_REQUIREMENTS.md` §4/workflow #4) is a separate, scheduled trigger, resolving what was an open gap during implementation planning (no fiscal-year field existed anywhere in `04_DATABASE.md` until 2026-09-07) — same shape as Task's Overdue check (`03_ARCHITECTURE.md`: "no user action to hang that check off of"), a Celery Beat job that reads each org's `organizations.fiscal_year_start_month` (added to Cluster 1, ships in M2, `DEFAULT 1` so calendar-year quarters work automatically for any org that doesn't customize it), scans for orgs whose fiscal quarter just ended, and re-runs suggestion generation additively.
**Depends on:** M2 (`organizations.fiscal_year_start_month`, for the scheduled trigger), M4, M6 (suggestions read department/position/OKR context — `06_AI_DESIGN.md`'s `missing_department` row specifically reads existing OKRs as prompt context, a read dependency, not a foreign key).

### M8 — Performance: KPI Definitions & Weighting
**Backend:** `kpis` (Cluster 5). `POST|GET|PATCH /kpis`, weight-sums-to-100-per-group validation (app-level, 409 on drift). Add `kpi_weight` as the fourth `ai_suggestions.suggestion_type`, reusing M7's engine. `GET /ai-usage` (endpoint ships here; its screen doesn't land until M13, merged with Billing History, not overlooked, just paired later).
**Frontend:** KPI setup per department, AI-suggested weight split shown in the same review pattern as M7. **Also here: assemble the full onboarding wizard** — this is the last module in the onboarding sequence, so it's where Business DNA (M5) → Org Setup (M4) → OKRs (M6) → AI Suggestions for Critical Roles (M7) → KPIs (this milestone) → Invite Team (M2) get stitched into one wizard with the corrected step order (`08_DECISIONS.md` 2026-09-02 — Critical Roles sit between OKRs and KPIs, not after both).
**Depends on:** M6 (`key_result_id`), M7 (kpi_weight suggestion reuses the engine).

### M9 — Attendance
**Backend:** `attendance_records` (Cluster 7). `POST /attendance/clock-in|clock-out`, `GET /attendance`. "Currently clocked in" derived (`clock_out_at IS NULL`).
**Frontend:** Employee clock-in/clock-out widget. Also removes the existing Morning/Evening/Night shift-scheduling grid UI from the Journey Walkthrough deck implementation — MVP attendance is plain clock-in/clock-out only (`08_DECISIONS.md` 2026-09-02).
**Depends on:** M4 (`employee_id`).

### M10 — Task
**Backend:** `tasks` (Cluster 6). Standalone task CRUD, `POST /tasks/{id}/complete`, KPI-weight inheritance (calls Performance's service), clock-in-gated task list (calls Attendance's service — task list only visible post-clock-in), overdue as derived state + Celery Beat scan that notifies assignee + department manager the moment `due_at` passes. Filters: department, assignee, status, kpi, overdue.
**Frontend:** Employee daily task list (post-clock-in gate, sortable High→Medium→Low), Assign Task screen (KPI link, due date), task detail/complete action.
**Depends on:** M8 (KPI weight lookup), M9 (clock-in check).

### M11 — Workflow
**Backend:** `workflow_templates`, `workflow_steps`, `workflow_instances` (Cluster 6). Template/step CRUD (HR Administrator or any Manager), `POST /workflow-instances` (start a case), completing a step's task auto-creates the next step's task via Task's service (never a direct `tasks` insert), default-assignee-or-manager-delegation routing, same department allowed to repeat across steps.
**Frontend:** Workflow Template builder (ordered steps, department, turnaround, optional default assignee), Start Workflow Instance screen, instance status/progress view.
**Depends on:** M10 (Workflow only ever calls Task's service, never the other way).

### M12 — Performance: Scoring, Dashboards & Executive Intelligence
**Backend:** `kpi_scores` recording (`POST /kpis/{id}/scores`, `score_percentage` calc incl. inverse KPIs), `GET /departments/{id}/performance-summary` (quarterly revenue-target rollup), `employee_kpi_scores` (Cluster 5 — computed from each employee's tasks linked to a KPI, `due_at`/`completed_at` timeliness), `GET /employees/leaderboard`, `GET /company-performance-summary` (Company Performance Score, quarterly trend + custom range, Most Improved), `executive_summaries` + Celery Beat LLM narrative generation triggered on period recalculation.
**Frontend:** Manager/Executive dashboards — quarterly trend graph with custom date range, department drill-down to individual employees, employee leaderboard, Company Performance Score headline, Most Improved callout, AI-generated executive summary block. These are the investor-facing dashboard additions from `08_DECISIONS.md` 2026-09-07, treat visual polish here as first-class, not an afterthought.
**Depends on:** M10 (task timeliness data is the actual input to `employee_kpi_scores`), M11 (workflow-generated tasks also feed scoring).

### M13 — Billing & Platform Admin
**Backend:** `billing_records`, `organizations.subscription_status`/`subscription_expires_at` (Cluster 1). `GET /billing/history` (Owner/HR Administrator). Uses the `platform_admin` (`BYPASSRLS`) role and `scripts/admin/` already provisioned in M1 to set these fields manually — no role creation here, this milestone only adds the billing-specific admin scripts and the read endpoint. Every invocation audit-logged (M3).
**Frontend:** **Admin Settings screen — Billing History + AI Usage combined**, one settings area, not two separate pages (`GET /billing/history` from this milestone, `GET /ai-usage` shipped back in M8). Owner/HR Administrator only, read-only, no payment page, no checkout, Paystack/Flutterwave handle the actual invoice and payment.
**Depends on:** M2 (organizations), M3 (audit log for admin-script invocations), M8 (`GET /ai-usage` already exists by this point).

### M14 — Security Hardening
**Backend:** Rate limiting on `/auth/login` and `/auth/refresh` (`slowapi` or reverse-proxy layer). CORS allow-list finalized for real staging/prod origins. Secrets audit (`.env`/`.mcp.json` never committed, rotation check for anything ever exposed). HTTPS/TLS enforced past local dev. NDPA data-protection flag surfaced as an explicit "needs legal sign-off" checklist item, not silently treated as compliant.
**Frontend:** Surface rate-limit/lockout error states on login.
**Depends on:** M2 (auth endpoints exist to rate-limit).

### M15 — Deployment & Demo Readiness
**Backend:** `docker-compose.prod.yml`, hosting deploy (Railway dev / Azure prod per `00_PROJECT_CONTEXT.md`, pending CloudSA conversation), seed script populating Elevare itself as tenant #1 (real departments, OKRs, critical roles, KPIs) as demo data, end-to-end smoke test across onboarding → daily execution → dashboards.
**Frontend:** Production build/deploy, final polish pass specifically on investor-facing screens (executive dashboard, AI suggestion review, onboarding wizard) — this MVP is demoed to investors and public figures per project context.
**Depends on:** all prior milestones.

## Trello cross-check (2026-09-07, actioned same day)

Cross-checked this plan against the "Elevare Workforce OS" Trello board (To Do / Doing / Done). Three gaps found, all now actioned directly on the board, not just noted here:
- **Duplicate "[Backend] Audit Log module" card** (positions 1500 and 3500, same list) — the newer one (created a day after the original, no comments/checklists on either) archived. The original at position 1500 stands.
- **"[Backend] Notifications module" card was queued at position 23000** in To Do, right before Workflow's frontend and the Executive dashboard card — far later than Audit Log (1500), despite `02_SYSTEM_DESIGN.md` treating both as the same category of early infrastructure and M3 above bundling them together. Left as-is, M7 (AI Suggestions, resurfaces via notifications) and M11 (Workflow approvals) would reach a queue position for a service that hadn't been started yet. **Moved to position 1600**, right after Audit Log, matching M3's build order.
- **M14 (Security Hardening) and M15 (Deployment & Demo Readiness) had no matching cards.** Added: `[Backend] Security Hardening`, `[Backend] Deployment & Demo Readiness`, `[Frontend - Uche] Production build & investor-facing polish pass`, all in To Do at positions 26000–28000, after the existing Executive dashboard card.
