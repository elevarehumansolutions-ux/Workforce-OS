# Database Design

Built incrementally, cluster by cluster, each depending on the one before it. See `01_REQUIREMENTS.md` and `08_DECISIONS.md` for the product reasoning behind each entity — this doc is the schema itself.

## Conventions (apply to every table below unless noted)
- **UUID primary keys**, not auto-incrementing integers — sequential IDs let someone guess adjacent records and leak row counts, which matters more in a multi-tenant system than most.
- **`organization_id` on every tenant-scoped table**, enforced by the Postgres Row-Level Security policy decided in `08_DECISIONS.md` (2026-09-04).
- **`created_at` / `updated_at`** on every table.
- **Soft delete** (`deleted_at`, nullable) on core entities — old records (KPIs, tasks, performance history) should still be able to reference "a department that used to exist" rather than break.

## Cluster 1: Tenancy & Identity

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,                       -- nullable: NULL until Business DNA onboarding sets it (see 08_DECISIONS.md 2026-09-13)
    subscription_status TEXT NOT NULL DEFAULT 'trial' CHECK (subscription_status IN ('trial','active','expired','cancelled')),
    subscription_expires_at TIMESTAMPTZ,
    fiscal_year_start_month SMALLINT NOT NULL DEFAULT 1 CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT,              -- nullable: a user added later via SSO may have none
    auth_provider TEXT NOT NULL DEFAULT 'password',
    account_status TEXT NOT NULL DEFAULT 'pending_verification' CHECK (account_status IN ('pending_verification','verified','suspended','deactivated','banned')),
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('hr_administrator','manager','business_executive','employee','system_administrator')),
    is_owner BOOLEAN NOT NULL DEFAULT false,
    deactivated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_id)
);
```

```sql
CREATE TABLE billing_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    description TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'NGN',
    paid_at DATE NOT NULL,
    provider TEXT CHECK (provider IN ('paystack','flutterwave','bank_transfer')),
    provider_reference TEXT,
    recorded_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- **`billing_records`, added 2026-09-07, is a payment history log, not an invoice generator.** The actual invoice/receipt is created and sent through Paystack or Flutterwave's own invoicing feature, not built here, same reasoning as not building custom payment processing at all. This table exists purely so an Owner or HR Administrator can see "what's been paid, and when" inside the product itself. Populated manually by Elevare staff (via the same admin process that sets `subscription_status`) whenever a payment is confirmed, `provider_reference` ties a row back to the real Paystack/Flutterwave transaction if it ever needs tracing. Read-only from the product's side, nothing in the app writes to this table except that manual process.
- `users` has no `organization_id` — a User is just a person with an email and password; a `Membership` is what says "this person belongs to this company, with this role." This is the identity-separate-from-org-role pattern from the signup decision (whoever signs up first becomes Owner). `users` itself needs no RLS; the tenant boundary starts at `memberships`.
- `is_owner` is a flag, not a role value, because it answers a different question (account-level authority, billing, un-removable) than `role` does (product permissions). A membership can be `role = 'hr_administrator', is_owner = true` simultaneously.
- **`memberships.deactivated_at`, added 2026-09-18.** Deactivating a teammate is scoped to this one membership, not the person's `User.account_status` globally — someone deactivated from one organization keeps full, working access to any other organization they belong to. `NULL` = active. Not the `deleted_at` soft-delete convention: a deactivated membership is still a real, current row (still listed in Team Management, still shows up as "deactivated" in the org-switcher), not a stand-in for something that used to exist. See `08_DECISIONS.md` 2026-09-18 for the two deeper RLS bugs this fix surfaced.
- **`organizations.fiscal_year_start_month`, added 2026-09-07, closes a real gap.** `01_REQUIREMENTS.md` §4 and Main Workflow #4 require the Quarterly Objective Review to trigger "at each quarter's end, per the org's configured fiscal year," but no field ever existed to store that. Lives on `organizations`, not `business_dna`, because it's operational/platform configuration, same category as `subscription_status` right above it, not business-identity content like vision or mission. `DEFAULT 1` (January) means standard calendar-year quarters happen automatically for every org that doesn't customize it, satisfying the requirement for real rather than quietly cutting it, at the cost of one column with a sane default.
- **`organizations.subscription_status`/`subscription_expires_at`, added 2026-09-07.** Billing for MVP is manual (see `08_DECISIONS.md`): Elevare invoices a customer, they pay via a Paystack/Flutterwave payment link or bank transfer, and Elevare staff sets these two fields through the internal admin scripts already designed for the RLS-bypass role (`07_SECURITY.md`), the same tooling used for other cross-customer administrative work. **No automated enforcement reads these fields in MVP** — deliberately. With a small, closely-managed set of pilot/demo customers, building expiry-enforcement logic now risks locking out someone who actually paid but whose status update hasn't landed yet, more risk than a manual process carries at this scale. These fields exist for visibility and record-keeping now; automated access enforcement is Phase 2, once real customer volume justifies it.
- **`organizations.name` is nullable, added 2026-09-13.** Registration is identity-only (name, work email, password — see the 2026-09-02 signup decision); company name isn't captured until the Business DNA onboarding step (M5). But the org row has to exist at registration time, since the founding Owner's `Membership` references it. See `08_DECISIONS.md` 2026-09-13.
- **`users.account_status`, added 2026-09-13, is the single source of truth for account state** (`pending_verification`/`verified`/`suspended`/`deactivated`/`banned`) — matches what M1's stubbed `get_current_user` already expected to check. No separate `is_active`/`is_verified` booleans, deliberately, so there's exactly one field to read or update, not several that can silently disagree with each other.

## Cluster 2: Org Structure

```sql
CREATE TABLE locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    is_critical BOOLEAN NOT NULL DEFAULT false,
    revenue_allocation_percentage NUMERIC(6,2),  -- only meaningful if is_critical; can exceed 100
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    department_id UUID NOT NULL REFERENCES departments(id),
    title TEXT NOT NULL,
    is_critical BOOLEAN NOT NULL DEFAULT false,
    criticality_type TEXT CHECK (criticality_type IN ('revenue_generating','revenue_enabling','operational','customer','compliance','strategic')),
    risk_level TEXT CHECK (risk_level IN ('low','medium','high')),
    reports_to_position_id UUID REFERENCES positions(id),  -- structural org-chart shape, nullable at the top
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID REFERENCES users(id),          -- nullable: an employee can exist before being invited to log in
    position_id UUID NOT NULL REFERENCES positions(id),
    manager_id UUID REFERENCES employees(id),   -- this specific person's actual manager
    location_id UUID REFERENCES locations(id),
    employee_code TEXT,                          -- display-friendly, e.g. "EMP-001", not the real key
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    work_email TEXT NOT NULL,
    phone_number TEXT,
    address TEXT,
    employment_type TEXT CHECK (employment_type IN ('full_time','part_time','contract','intern')),
    start_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
```

**Design notes:**
- **Criticality lives on `positions`, revenue allocation lives on `departments`** — the two-level split Jennifer confirmed (General Manager the position, Operations the department). `criticality_type` and `risk_level` match the tags on the AI Suggestions screen in the Journey Walkthrough deck.
- **`organization_id` appears on every table here**, even though it's reachable through `department_id` or `position_id`. Deliberate duplication: RLS policies need the column directly present to check the tenant boundary without a join on every query.
- **Two different "reporting" concepts exist, on purpose:** `positions.reports_to_position_id` is the structural org chart (which role reports to which role, independent of who holds them); `employees.manager_id` is a specific person's actual assigned manager. They'll usually agree, but the Journey Walkthrough deck designed both separately (position-level org-chart setup, plus a person-level "Reporting Manager" field on Add Employee).
- **`employees.user_id` is nullable** because the Add Employee screen has a "grant login access" checkbox — someone can exist in the org structure before ever being invited to log in.
- **`employees.address` added 2026-09-20** during implementation (not in the original PRD field list) — a plain optional text field for the employee's own address, distinct from `locations.address` (the office/site they work out of).
- **`employees.status` has no `'on_leave'` value.** It was originally included on the assumption a Leave module would set it, but Leave Management moved to Phase 2 (see `08_DECISIONS.md`, 2026-09-04) with no manual fallback wanted either. Just `'active'`/`'inactive'` for MVP; revisit when Leave Management is actually built.
- **Soft-deleting a department or position is blocked, not cascaded, while active references exist** (active employees still assigned, open/in-progress tasks, a pending AI suggestion), enforced in application code, not the database, since it needs to check across multiple tables and return a specific, named reason. Added 2026-09-07, see `01_REQUIREMENTS.md` §2 and `08_DECISIONS.md`.
- **Not modeled yet, flagged honestly:** the PRD mentions "business units" above departments. Nothing in our conversations stress-tested whether that needs its own table or is just a grouping label. Left out for now rather than guessed; add it if it turns out to matter.
- **Filtering by location:** a company can have multiple offices (e.g. Abuja and Lagos); listing employees org-wide by default shows everyone across all of them, that's correct default behavior. `employees.location_id` is what makes narrowing to one location possible (`WHERE organization_id = :org_id AND location_id = :location_id`), matching the "Location" filter already on the Employee Directory screen in the Journey Walkthrough deck. Indexed below to keep it fast as headcount grows:

```sql
CREATE INDEX idx_employees_org_location ON employees(organization_id, location_id);
```

## Cluster 3: Business DNA

```sql
CREATE TABLE business_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL UNIQUE REFERENCES organizations(id),  -- one per org
    industry TEXT,
    products_services_description TEXT,
    vision TEXT,
    mission TEXT,
    business_model TEXT,
    performance_philosophy TEXT,
    workforce_rules TEXT,
    revenue_drivers TEXT,
    operational_drivers TEXT,
    customer_value_drivers TEXT,
    capital_investment_amount NUMERIC(14,2),  -- feeds department revenue allocation, Cluster 4
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE business_dna_core_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    business_dna_id UUID NOT NULL REFERENCES business_dna(id),
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- **No "strategic objectives" or "OKRs" field here, on purpose.** The original Business DNA screen had this, but it's a duplicate once the dedicated OKR step exists (Cluster 4), objectives belong there, not here, or they'd be captured twice.
- **Core values as a separate table, not a text field or JSONB column.** Either would have worked, JSONB (`core_values JSONB DEFAULT '[]'` directly on `business_dna`) is a completely valid alternative for a simple list like this, arguably the more common modern Postgres pattern when nothing extra needs attaching to each value. The table was chosen instead to leave room for querying or extending individual values later (e.g. Elevare, as the vendor, comparing which core values are common across customers), a judgment call, not a correctness issue.
- **One `business_dna` row per organization**, editable in place, not versioned. Historical comparison (e.g. "what was our capital investment last year") is a future refinement, not something asked for yet.
- **`business_dna_core_values` has `updated_at`, matching the top-level Conventions rule.** Editing a value updates its row in place, same as everywhere else in this schema, rather than modeling an edit as delete-and-reinsert.
- **"Job architecture" isn't a separate field here** — it's already the `positions` table from Cluster 2.

## Cluster 4: Strategy — OKRs and AI Suggestions

```sql
CREATE TABLE okrs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    department_id UUID REFERENCES departments(id),  -- null = corporate OKR, set = departmental OKR
    location_id UUID REFERENCES locations(id),  -- null = applies org/department-wide; set = scoped to one location (branch/store model)
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE key_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    okr_id UUID NOT NULL REFERENCES okrs(id),
    description TEXT NOT NULL,
    target_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE ai_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    suggestion_type TEXT NOT NULL CHECK (suggestion_type IN ('critical_position','revenue_allocation','missing_department','kpi_weight')),
    position_id UUID REFERENCES positions(id),                 -- set for 'critical_position'
    department_id UUID REFERENCES departments(id),              -- set for 'revenue_allocation'
    kpi_id UUID REFERENCES kpis(id),                             -- set for 'kpi_weight'
    suggested_department_name TEXT,                              -- set for 'missing_department' only — no row exists yet
    suggested_criticality_type TEXT,
    suggested_risk_level TEXT,
    suggested_revenue_allocation_percentage NUMERIC(6,2),
    suggested_weight NUMERIC(5,2),                               -- set for 'kpi_weight'
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','edited','rejected')),
    reviewed_by_user_id UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    reviewed_criticality_type TEXT,                              -- final human decision, set on approve or edit, mirrors suggested_criticality_type
    reviewed_risk_level TEXT,                                     -- mirrors suggested_risk_level
    reviewed_revenue_allocation_percentage NUMERIC(6,2),          -- mirrors suggested_revenue_allocation_percentage
    reviewed_department_name TEXT,                                -- mirrors suggested_department_name
    reviewed_weight NUMERIC(5,2),                                 -- mirrors suggested_weight
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (suggestion_type = 'critical_position' AND position_id IS NOT NULL) OR
        (suggestion_type = 'revenue_allocation' AND department_id IS NOT NULL) OR
        (suggestion_type = 'missing_department' AND suggested_department_name IS NOT NULL) OR
        (suggestion_type = 'kpi_weight' AND kpi_id IS NOT NULL)
    )
);
```

**Design notes:**
- **`okrs`/`key_results` need nothing special for "additive, never clears."** That requirement, confirmed 2026-09-02, falls out of the schema for free: adding an objective mid-quarter is just inserting a new row, existing ones are untouched by default.
- **`okrs.location_id` is nullable, and stays null for a headquarters-plus-satellite-offices business like Elevare** — one team, one set of targets, regardless of which office people sit in. It exists for the other shape of customer this product will also serve: a retail chain or branch-based business where each location is effectively its own business unit with its own targets (e.g. Lagos Store vs Abuja Store). Set = scoped to that one location; null = applies to the whole department. `departments` itself is untouched, a department is never owned by a location, only individual OKRs/KPIs optionally are.
- **`ai_suggestions` is the new idea in this cluster.** Without it, `positions.is_critical` and `departments.revenue_allocation_percentage` would have to already be true the moment AI proposes them, skipping the "human approves" step the AI approach requires. This table holds the in-between state, proposed but not yet real, visible on the AI Suggestions review screen (Approve/Edit/Reject). Once HR approves or edits one, the application writes the final value onto the real `positions` or `departments` row; for a missing-department suggestion, onto a newly created `departments` row.
- **One table for three suggestion types, not three tables.** A genuine tradeoff, not a clean answer: three separate tables would avoid the unused nullable columns per type, but would repeat the same pending/approved/edited/rejected review lifecycle three times over. One table was the more pragmatic call for MVP.
- **A CHECK constraint enforces the type-to-column pairing** (`critical_position` requires `position_id`, `revenue_allocation` requires `department_id`, `missing_department` requires `suggested_department_name`) — without it, nothing would stop a nonsensical row like a `critical_position` suggestion with no position attached. Caught during the consistency pass on 2026-09-04, not part of the original draft.
```sql
CREATE UNIQUE INDEX idx_ai_suggestions_unique_pending
ON ai_suggestions (organization_id, suggestion_type, position_id, department_id, kpi_id, suggested_department_name)
WHERE status = 'pending';
```
- **The partial unique index above (2026-09-07) makes retried Celery generation jobs safe.** Without it, a retried "generate suggestions" job could create a second, duplicate pending suggestion for the same target. Postgres treats NULL columns as never conflicting, so this one index correctly enforces "one pending suggestion per target" across all four suggestion types without needing a separate index per type. Paired with `INSERT ... ON CONFLICT DO NOTHING` in the generation code, a retry becomes a safe no-op instead of a duplicate row.
- **`kpi_weight` added as a fourth `suggestion_type`, 2026-09-05**, closing a gap against `01_REQUIREMENTS.md` §7/§8: "AI suggests a starting split when KPIs are set up, HR approves/edits, same pattern used everywhere else." The original three types missed this entirely. Follows the exact same shape as the other three: a type-specific target (`kpi_id`), a suggested value, a reviewed value, and the same CHECK-constraint pairing.
- **`reviewed_*` columns mirror each `suggested_*` column, added 2026-09-05.** This table isn't just a review queue, it's the raw material for eventually training a proprietary model once enough organizations have gone through it (see `01_REQUIREMENTS.md` §8, "approvals/corrections become future training data"). Without a place to record what HR actually decided, the table would only ever remember what the AI proposed, the single most valuable signal, "AI suggested X, human corrected it to Y", would be lost. `reviewed_*` gets populated whenever a decision is made, approved **or** edited, not only on edits, so anything reading this later for training data has one consistent column to read from, instead of branching on `status` to decide whether to trust `suggested_*` or `reviewed_*`. On `rejected`, `reviewed_*` stays null, there's no "correct" value to record, the rejection itself is the signal.
```sql
CREATE TABLE ai_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    purpose TEXT NOT NULL CHECK (purpose IN ('ai_suggestion_generation','executive_summary_generation')),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    estimated_cost_usd NUMERIC(10,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
- **`ai_usage_log`, added 2026-09-07.** One row per actual LLM call, not per suggestion, a single call can produce several suggestions at once (one department's positions analyzed together), so cost has to attach to the call itself, not be arbitrarily split across its results. Both AI Suggestions and Performance's executive-summary generation write here, through a small shared internal LLM-calling utility rather than each duplicating their own "how do I call Claude" code, same discipline as everywhere else in this schema, one place for a piece of logic. `GET /ai-usage` (an org's own HR Administrator, normal RLS) shows that org's own usage; aggregate cost across every customer goes through the same internal admin scripts already built for billing, not a new access pattern.
- **Quarterly revenue targets aren't a stored table.** The annual target is `departments.revenue_allocation_percentage / 100 × business_dna.capital_investment_amount`; the quarterly figure is that divided by four, computed when needed. If uneven quarter-by-quarter splits become a real requirement later, that's worth a table then, not speculatively now.

## Cluster 5: KPIs

```sql
CREATE TABLE kpis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    department_id UUID NOT NULL REFERENCES departments(id),
    location_id UUID REFERENCES locations(id),  -- null = department-wide; set = scoped to one location (branch/store model)
    key_result_id UUID REFERENCES key_results(id),
    name TEXT NOT NULL,
    weight NUMERIC(5,2) NOT NULL CHECK (weight >= 0 AND weight <= 100),
    target_value NUMERIC(14,2),
    unit TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE kpi_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    kpi_id UUID NOT NULL REFERENCES kpis(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    actual_value NUMERIC(14,2),
    score_percentage NUMERIC(5,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- **`kpis.weight` is per-department (or per-location, when `location_id` is set), not enforced by the database to sum to 100.** Postgres has no clean row-level way to check "all weights for this group add up to 100," that math spans multiple rows. This is validated in application code when a KPI is created or edited (reject or warn if the group's total would drift from 100). An app-layer rule, not a database guarantee.
- **`kpis.location_id` mirrors the `okrs.location_id` decision above, same reasoning.** Null for Elevare, everywhere. Available for a branch-based customer that needs "Lagos store" and "Abuja store" scored separately within the same department.
- **`key_result_id` is nullable on purpose.** Not every KPI needs to trace back to a specific Key Result, some departments have operational KPIs (e.g. "average response time") that support the strategy generally without tying to one measurable OKR target. Making it mandatory would force a fake link where none exists.
- **`kpi_scores` is one row per KPI per scoring period** (a quarter, matching the quarterly dashboard), not a running single value on `kpis` itself. This is what lets the performance dashboard show a trend over time, and it's what the weighted scoring calculation reads from to compute a department's (or location's) overall performance for that period.
- **`score_percentage` is stored, not computed on the fly**, because how "actual vs target" becomes a percentage isn't always a straight ratio (a KPI can be inverse, e.g. lower is better for "customer complaints"). The calculation logic lives once in application code, and the result is written here rather than every dashboard query re-deriving it differently.
- **`kpi_scores` has no `deleted_at`, a deliberate exception to the top-level Conventions rule** that names "performance history" as needing soft delete. A scoring record for a closed period is a historical fact, not something that should ever disappear, even softly. If a score turns out wrong, the correction is a new period's record, not hiding the old one. Same reasoning as `workflow_instances` having no `deleted_at`, decided during the 2026-09-04 consistency pass.

```sql
CREATE TABLE employee_kpi_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    kpi_id UUID NOT NULL REFERENCES kpis(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    score_percentage NUMERIC(5,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE executive_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    summary_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Added 2026-09-07, closing a real gap, not new scope:** `01_REQUIREMENTS.md` §11 (confirmed with Jennifer, 2026-09-02) already required that clicking a department drill down to "how each person's performance rolls up into the department's overall score." That was written down but never modeled, `kpi_scores` only ever captured a department's score, nothing captured an individual's. `employee_kpi_scores` is that missing piece, same shape as `kpi_scores`, computed from that employee's own tasks linked to each KPI (`tasks.kpi_id`, their `due_at`/`completed_at` timeliness), one row per employee per KPI per period. This is also what a leaderboard/"high performing employees" view reads from, and what "Most Improved" compares period over period, neither needs its own stored table, both are cheap aggregate/comparison queries over data already sitting here.
- **`executive_summaries` is genuinely new scope, added 2026-09-07** for the investor-facing dashboard: a short LLM-generated narrative of a period's performance ("Operations exceeded target by 12%..."). Stored, not generated on every dashboard load, an LLM call is too slow and too costly to run per page view. Generated periodically by Celery Beat (same pattern as the Overdue check in Cluster 6), triggered whenever a period's `kpi_scores`/`employee_kpi_scores` are recalculated, not on every request.

## Cluster 6: Tasks & Workflow

```sql
CREATE TABLE workflow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    department_id UUID NOT NULL REFERENCES departments(id),  -- the department that owns/authored this template
    name TEXT NOT NULL,
    created_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE workflow_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    workflow_template_id UUID NOT NULL REFERENCES workflow_templates(id),
    step_order INTEGER NOT NULL,
    name TEXT NOT NULL,
    department_id UUID NOT NULL REFERENCES departments(id),  -- can differ from the template's owning department
    default_assignee_employee_id UUID REFERENCES employees(id),
    default_turnaround_hours INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE workflow_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    workflow_template_id UUID NOT NULL REFERENCES workflow_templates(id),
    subject TEXT NOT NULL,
    started_by_user_id UUID REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','cancelled')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    workflow_instance_id UUID REFERENCES workflow_instances(id),  -- null = standalone, ad hoc task
    workflow_step_id UUID REFERENCES workflow_steps(id),           -- which step this came from, null for standalone
    department_id UUID NOT NULL REFERENCES departments(id),
    kpi_id UUID REFERENCES kpis(id),  -- null = not linked to a KPI; when set, task inherits kpis.weight (§7)
    assigned_to_employee_id UUID REFERENCES employees(id),
    title TEXT NOT NULL,
    description TEXT,
    due_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed','cancelled')),
    created_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
```

**Design notes:**
- **One `tasks` table for both workflow-generated and standalone tasks.** `workflow_instance_id`/`workflow_step_id` are nullable so an ad hoc task (a manager just typing "follow up with vendor" with no template behind it) uses the exact same table and the exact same dashboard, rather than needing a second parallel task system.
- **"Overdue" is not a stored status, it's derived: `status IN ('open','in_progress') AND due_at < now()`.** It isn't a state anyone chooses, it's a fact that becomes true the moment the clock passes `due_at` while nobody's touched the status. Storing it as an enum value would mean either a background job flipping it constantly, or it going stale between checks. Computing it at query/read time is simpler and always correct.
- **Late completion is also derived, from history, not stored as a flag: `completed_at > due_at`.** Since both timestamps are just sitting on the row, "was this done on time" is answerable forever, even long after the task is closed, which is exactly what has to feed the performance-scoring calculation later.
- **`due_at` is written onto the task itself when it's created, not read from `workflow_steps.default_turnaround_hours` every time it's displayed.** The turnaround on the step is a template default used once, at creation, to compute a concrete deadline. If someone edits the template's default turnaround afterward, already-created tasks must not silently shift, that would be changing history.
- **`tasks.kpi_id` is nullable, and links a task to the KPI it counts toward.** Added 2026-09-05, closing a gap against `01_REQUIREMENTS.md` §5 ("Tasks link to employee, department, KPI, and org objective") and §7 (a linked task "automatically inherits the linked KPI's weight"). This is also what gives a task traceability all the way up to a corporate objective without needing its own `okr_id` column, `tasks.kpi_id` → `kpis.key_result_id` → `okrs.id` is the full chain, one column, not three.
- **`workflow_steps.department_id` can differ from `workflow_templates.department_id`.** This is what makes cross-department workflows possible, an Onboarding template owned by HR can still have a step that lands on IT and another that lands on Finance.
- **`default_assignee_employee_id` on the step is only a pre-fill.** The actual task's `assigned_to_employee_id` is what's authoritative at runtime, someone can override the default per instance without touching the template. A step with no default (like Operations' orientation step in the walkthrough) creates its task unassigned, and a manager assigns it manually once it appears in the department queue.
- **No branching or parallel steps, on purpose.** `step_order` is a plain linear sequence. Conditional or parallel workflow steps are a real feature in mature tools (Jira, Salesforce Flow), but nothing discussed so far calls for it, this is a deliberate MVP simplification, not an oversight, worth revisiting if a customer's actual process turns out to branch.

## Cluster 7: Attendance

```sql
CREATE TABLE attendance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    clock_in_at TIMESTAMPTZ NOT NULL,
    clock_out_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- **One row per clock-in/clock-out pair, that's the whole table.** "Currently clocked in" is derived (`clock_out_at IS NULL`), the same pattern as Overdue in Cluster 6, a fact computed from timestamps rather than a status column someone has to remember to flip.
- **No `location_id` here.** Plain clock-in/clock-out doesn't need to record where someone clocked in from for MVP, no geofencing or per-site attendance requirement has come up. If that ever matters, the employee's `location_id` is already sitting on their row in Cluster 2.
- **This table only feeds the task-visibility rule already in §5**, "task list appears after clock-in," it's read, not written, by that check. No leave-status interaction — see the `employees.status` note in Cluster 2.

## Cluster 8: Notifications

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    recipient_user_id UUID NOT NULL REFERENCES users(id),
    category TEXT NOT NULL CHECK (category IN ('ai_suggestion','approval_request','task','system')),
    title TEXT NOT NULL,
    body TEXT,
    link_type TEXT,
    link_id UUID,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- **`recipient_user_id` is a specific person, not a role.** The "role-specific stream" requirement (Employee/Manager/HR/Executive each seeing different notifications) doesn't need a role column at all, it's satisfied by who the notification gets addressed to at creation time. An AI suggestion notification targets the HR Administrators of that org; an approval-request notification targets that specific manager. Each person's stream is just "notifications where `recipient_user_id` = me," which is role-correct because of who was targeted, not because the table tracks roles.
- **`link_type` + `link_id` is a loose, unenforced pointer, not a real foreign key, unlike everywhere else in this schema.** A notification can point at an AI suggestion, a task, a workflow instance, a KPI, or something added later, more target types than anywhere else modeled here. A real FK per type would mean a growing pile of nullable columns that gets worse with every new notification-worthy event. The cost: the database can't guarantee `link_id` points at something real, that check moves to application code.
- **`read_at` nullable, not a boolean.** Null means unread; a timestamp means both "read" and "when," at no extra cost.
- **`category` matches the "filterable by category" requirement directly.**

## Cluster 9: Audit Log (added 2026-09-06)

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    actor_user_id UUID REFERENCES users(id),  -- null = system/background action, not a person
    action TEXT NOT NULL,                      -- e.g. 'create', 'update', 'delete', 'approve_suggestion'
    entity_type TEXT NOT NULL,                 -- e.g. 'department', 'position', 'kpi', 'ai_suggestion'
    entity_id UUID NOT NULL,
    changes JSONB,                             -- what changed, shape varies by entity_type
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_org_entity ON audit_log(organization_id, entity_type, entity_id);
```

**Design notes:**
- **`entity_type` + `entity_id` is a loose pointer, not a real foreign key, same tradeoff already accepted for `notifications.link_type`/`link_id`.** An audit log has to be able to reference literally any table in the system, a real FK per entity type would mean an ever-growing list of nullable columns here, worse than anywhere else this tradeoff has come up, since audit log needs to cover everything, not just three or four types.
- **`changes` is JSONB, not a fixed set of columns**, because what changed on a `department` looks nothing like what changed on a `kpi`. This is the same shape-varies-by-type problem as `ai_suggestions`, but with far more types than four, JSONB is the pragmatic choice here where mirrored typed columns isn't.
- **No `deleted_at`.** An audit log entry is a historical fact, same reasoning as `kpi_scores`, it should never be removable, soft-deleted or otherwise, that would defeat the point of it existing.
- **`actor_user_id` is nullable** for actions a background job takes on its own (e.g. the Overdue check flipping a task's visibility isn't a person acting, though notice the check itself doesn't mutate the task row, since Overdue is derived, not stored, so this mostly matters for Celery-triggered writes, like AI Suggestions' LLM-generated proposals, `actor_user_id` null there since no human initiated that particular row's creation).
