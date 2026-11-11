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
    timezone VARCHAR(64) NOT NULL DEFAULT 'Africa/Lagos',  -- IANA name; where "midnight" falls for the attendance auto-close (2026-10-02)
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
    name_normalized TEXT NOT NULL GENERATED ALWAYS AS (
        lower(regexp_replace(btrim(normalize(name, NFKC)), '\s+', ' ', 'g'))
    ) STORED,                                    -- database-derived comparison key, never written by the app
    is_critical BOOLEAN NOT NULL DEFAULT false,
    revenue_allocation_percentage NUMERIC(6,2),  -- only meaningful if is_critical; can exceed 100
    head_employee_id UUID REFERENCES employees(id),  -- the one employee HR names as head; null until set (2026-10-06)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_departments_org_name_active
ON departments (organization_id, name_normalized)
WHERE deleted_at IS NULL;

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
- **`departments.head_employee_id` — "department manager" (added 2026-10-06, `08_DECISIONS.md`).** A nullable link to one employee, set by HR. It answers "who heads this department?" with exactly one value, which an `is_manager` flag on people cannot guarantee. Three different things are called "manager" in this product, and they are stored separately: the membership *role* `manager` (permissions), `employees.manager_id` (a person's own reporting manager), and this (a department's head). Rules, enforced in `DepartmentService` and `EmployeeService.offboard_employee`: optional; any active employee of the same organization (not necessarily a member of that department; one person may head several); cleared in the same transaction when the head is offboarded (audit entry per department, HR administrators notified, reinstating does not restore it). Deliberately a plain column with no ORM relationship. Foreign-key cycle to know about: `departments -> employees -> positions -> departments`. Later option: `departments.head_position_id`, so the head follows the position instead of the person.
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
- **No `name`/`organization_name` column here, on purpose.** The org's name lives on `organizations.name` (nullable post-registration, see `08_DECISIONS.md` 2026-09-13). `PUT /business-dna` writes it through in the same transaction as this table's upsert rather than duplicating it here — see `08_DECISIONS.md` 2026-09-21.
- **`capital_investment_amount` is restricted at the API/serialization layer, not RLS.** RLS enforces the tenant boundary (which org's row), not column-level visibility within a row a caller is already allowed to see — so this column is included in the `GET /business-dna` response only for `hr_administrator`/`business_executive` callers, handled by the response schema/service, same row for everyone otherwise. See `08_DECISIONS.md` 2026-09-21.

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
    suggestion_type TEXT NOT NULL CHECK (suggestion_type IN ('critical_position','revenue_allocation','missing_department')),
    position_id UUID REFERENCES positions(id),                 -- set for 'critical_position'
    department_id UUID REFERENCES departments(id),              -- set for 'revenue_allocation'
    suggested_department_name TEXT,                              -- set for 'missing_department' only — no row exists yet
    suggested_department_name_normalized TEXT GENERATED ALWAYS AS (
        lower(regexp_replace(btrim(normalize(suggested_department_name, NFKC)), '\s+', ' ', 'g'))
    ) STORED,                                                    -- database-derived comparison key, never written by the app
    suggested_criticality_type TEXT,
    suggested_risk_level TEXT,
    suggested_revenue_allocation_percentage NUMERIC(6,2),
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','edited','rejected')),
    reviewed_by_user_id UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    reviewed_criticality_type TEXT,                              -- final human decision, set on approve or edit, mirrors suggested_criticality_type
    reviewed_risk_level TEXT,                                     -- mirrors suggested_risk_level
    reviewed_revenue_allocation_percentage NUMERIC(6,2),          -- mirrors suggested_revenue_allocation_percentage
    reviewed_department_name TEXT,                                -- mirrors suggested_department_name
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (suggestion_type = 'critical_position' AND position_id IS NOT NULL
            AND suggested_criticality_type IS NOT NULL AND suggested_risk_level IS NOT NULL) OR
        (suggestion_type = 'revenue_allocation' AND department_id IS NOT NULL
            AND suggested_revenue_allocation_percentage IS NOT NULL) OR
        (suggestion_type = 'missing_department' AND suggested_department_name IS NOT NULL)
    )
);
```

**M7/M8 phasing, settled during M7 implementation (2026-09-23):** the block above is what M7 actually builds — three suggestion types only. `kpi_id`, `suggested_weight`, `reviewed_weight`, and the `kpi_weight` value of `suggestion_type` (all described in the 2026-09-05 decision below) are added by a separate `ALTER TABLE` migration in M8, once `kpis` exists — a `CREATE TABLE` referencing `kpis(id)` before that table exists would fail outright, and `09_PROGRESS.md`'s M8 entry ("add `kpi_weight` as the fourth `suggestion_type`, reusing M7's engine") already implied this split, just not stated here explicitly until now. `updated_at` is also added here (BaseModel gives every table one, and unlike an append-only log this row genuinely mutates — status and the `reviewed_*` columns change after creation), a harmless addition the original hand-drafted sketch simply hadn't included.

**Design notes:**
- **`okrs`/`key_results` need nothing special for "additive, never clears."** That requirement, confirmed 2026-09-02, falls out of the schema for free: adding an objective mid-quarter is just inserting a new row, existing ones are untouched by default.
- **`okrs.location_id` is nullable, and stays null for a headquarters-plus-satellite-offices business like Elevare** — one team, one set of targets, regardless of which office people sit in. It exists for the other shape of customer this product will also serve: a retail chain or branch-based business where each location is effectively its own business unit with its own targets (e.g. Lagos Store vs Abuja Store). Set = scoped to that one location; null = applies to the whole department. `departments` itself is untouched, a department is never owned by a location, only individual OKRs/KPIs optionally are.
- **`ai_suggestions` is the new idea in this cluster.** Without it, `positions.is_critical` and `departments.revenue_allocation_percentage` would have to already be true the moment AI proposes them, skipping the "human approves" step the AI approach requires. This table holds the in-between state, proposed but not yet real, visible on the AI Suggestions review screen (Approve/Edit/Reject). Once HR approves or edits one, the application writes the final value onto the real `positions` or `departments` row; for a missing-department suggestion, onto a newly created `departments` row.
- **One table for three suggestion types, not three tables.** A genuine tradeoff, not a clean answer: three separate tables would avoid the unused nullable columns per type, but would repeat the same pending/approved/edited/rejected review lifecycle three times over. One table was the more pragmatic call for MVP.
- **A CHECK constraint enforces the type-to-column pairing** (`critical_position` requires `position_id`, `revenue_allocation` requires `department_id`, `missing_department` requires `suggested_department_name`) — without it, nothing would stop a nonsensical row like a `critical_position` suggestion with no position attached. Caught during the consistency pass on 2026-09-04, not part of the original draft.
- **A `critical_position` suggestion must also carry `suggested_criticality_type` and `suggested_risk_level`, and a `revenue_allocation` one its `suggested_revenue_allocation_percentage` (2026-09-24)** — enforced by the same CHECK and mirrored in the create schema. Without them, approving one would flag a position critical with no description of why or how much. Both are required of the AI's answer; HR can still correct values on review (Edit). The approve write-through relies on this guarantee.
```sql
CREATE UNIQUE INDEX idx_ai_suggestions_unique_pending
ON ai_suggestions (organization_id, suggestion_type, position_id, department_id, suggested_department_name_normalized)
NULLS NOT DISTINCT
WHERE status = 'pending';
```
- **`suggested_department_name_normalized` (2026-09-23) — the index and the rejection lookup key on a derived comparison key, not the raw LLM-written name.** For `missing_department` the target's identity is free text, and an LLM won't reproduce it byte-for-byte across runs: a rejected "Customer Success" would come back as "Customer success" or "  Customer  Success", and both the pending-duplicate index and the rejected-suggestion suppression (`08_DECISIONS.md` 2026-09-22), comparing exactly, would treat it as a brand-new target — the same re-nagging the suppression rule exists to prevent. Standard practice (keep the display value, compare on a separate normalized key) applied as a Postgres generated column: NFKC Unicode normalization, trim, collapse internal whitespace, lowercase. Generated, not application-populated, so it can't drift from the source value and no write path can forget it; `suggested_department_name` itself stays exactly as the AI wrote it (display, and the unaltered signal for the training-data goal below). The same expression is defined once in `app/modules/ai/models.py` (`normalized_name_expr`) and reused for the query side, so the write side and read side can't disagree. **Scope of what this catches:** formatting noise (case, spacing, Unicode variants) — not synonyms or rewordings ("Customer Success Team" is a different key). Suppressing near-duplicate wording is a prompt-design concern for the generation step (e.g. telling the LLM which names were already rejected), not something a database key can do.
- **The partial unique index above (2026-09-07) makes retried Celery generation jobs safe.** Without it, a retried "generate suggestions" job could create a second, duplicate pending suggestion for the same target. Paired with `INSERT ... ON CONFLICT DO NOTHING` in the generation code, a retry becomes a safe no-op instead of a duplicate row.
- **`NULLS NOT DISTINCT` corrects a real bug found and verified against the dev DB during M7 implementation (2026-09-23).** This note originally claimed "Postgres treats NULL columns as never conflicting, so this one index correctly enforces one pending suggestion per target" — that has it backwards. Standard SQL unique-index semantics treat `NULL <> NULL` (never equal), so a composite unique index **never** fires when the differentiating columns are null. Every suggestion type here only populates one of `position_id`/`department_id`/`suggested_department_name`, leaving the other two null — meaning the index, as originally written, silently never caught a duplicate for *any* suggestion type, confirmed by directly inserting the same `critical_position`/`missing_department` target twice and watching both rows land. `NULLS NOT DISTINCT` (Postgres 15+; this project runs 16) makes the index treat two nulls in the same column as equal for uniqueness purposes, which is what the original description actually intended. Re-verified after the fix: an identical second insert is now correctly absorbed by `ON CONFLICT ... DO NOTHING`.
- **`kpi_weight` added as a fourth `suggestion_type`, 2026-09-05**, closing a gap against `01_REQUIREMENTS.md` §7/§8: "AI suggests a starting split when KPIs are set up, HR approves/edits, same pattern used everywhere else." The original three types missed this entirely. Follows the exact same shape as the other three: a type-specific target (`kpi_id`), a suggested value, a reviewed value, and the same CHECK-constraint pairing.
- **`reviewed_*` columns mirror each `suggested_*` column, added 2026-09-05.** This table isn't just a review queue, it's the raw material for eventually training a proprietary model once enough organizations have gone through it (see `01_REQUIREMENTS.md` §8, "approvals/corrections become future training data"). Without a place to record what HR actually decided, the table would only ever remember what the AI proposed, the single most valuable signal, "AI suggested X, human corrected it to Y", would be lost. The mirrored *value* columns (`reviewed_criticality_type`, `reviewed_risk_level`, `reviewed_revenue_allocation_percentage`, `reviewed_department_name`, and M8's `reviewed_weight`) get populated whenever a decision is made, approved **or** edited, not only on edits, so anything reading this later for training data has one consistent set of columns to read from, instead of branching on `status` to decide whether to trust `suggested_*` or `reviewed_*`. On `rejected`, those mirrored value columns stay null, there's no "correct" value to record, the rejection itself is the signal.
- **`reviewed_by_user_id`/`reviewed_at` are a different case from the mirrored value columns above, disambiguated during M7 implementation (2026-09-23): both are populated on every decision, including rejection.** They're plain audit fields (who, when), not a "what's the correct value" signal, so the "stays null on rejection" reasoning above doesn't apply to them, only to the mirrored `suggested_*`-shaped columns. This also isn't optional: the rejected-suggestion quarterly-suppression rule (`08_DECISIONS.md` 2026-09-22) compares a rejected row's `reviewed_at` against the org's current fiscal-quarter boundary to decide whether it's still suppressing regeneration — with no `reviewed_at` on a rejected row, that mechanism would have nothing to check.
```sql
CREATE TABLE ai_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    purpose TEXT NOT NULL CHECK (purpose IN ('ai_suggestion_generation','executive_summary_generation')),
    model TEXT NOT NULL,  -- model id that served the call, for per-model cost tracking (added 2026-09-25, model tiering)
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,  -- prompt-cache writes, 5m + 1h combined (added 2026-09-25)
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,   -- prompt-cache hits (added 2026-09-25)
    estimated_cost_usd NUMERIC(10,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
- **`ai_usage_log`, added 2026-09-07.** One row per actual LLM call, not per suggestion, a single call can produce several suggestions at once (one department's positions analyzed together), so cost has to attach to the call itself, not be arbitrarily split across its results. Both AI Suggestions and Performance's executive-summary generation write here, through a small shared internal LLM-calling utility rather than each duplicating their own "how do I call Claude" code, same discipline as everywhere else in this schema, one place for a piece of logic. `GET /ai-usage` (an org's own HR Administrator, normal RLS) shows that org's own usage; aggregate cost across every customer goes through the same internal admin scripts already built for billing, not a new access pattern.
- **Quarterly revenue targets aren't a stored table.** The annual target is `departments.revenue_allocation_percentage / 100 × business_dna.capital_investment_amount`; the quarterly figure is that divided by four, computed when needed. If uneven quarter-by-quarter splits become a real requirement later, that's worth a table then, not speculatively now.

### `blueprint_items` (added 2026-10-22, migration `f208d4e04adc`, RLS `tenant_isolation`)

The AI-proposed starting structure, held until HR reviews it. One row per proposed department, position, objective, key result, rename or note. Not part of `ai_suggestions` on purpose (that table models single-column proposals on rows that already exist; see `08_DECISIONS.md` 2026-10-22).

| Column | Meaning |
|---|---|
| `organization_id`, `batch_id` | owner; one generation run |
| `kind` | `department`, `position`, `objective`, `key_result`, `kpi`, `rename_department`, `rename_position`, `review_note`, `folded` (CHECK; `folded` added by migration `c41a9d7e2b85`) |
| `folded_into_ref` | only for `folded` (migration `c41a9d7e2b85`): the `ref` of the proposed department or position that covers the left-out one. When the cover already exists as a real row, `department_id` / `position_id` is set instead. The type of what was left out equals the type of what covers it. |
| `is_critical`, `revenue_allocation_pct`, `criticality_type`, `risk_level` | the AI's own decisions (migration `2830c100436f`): for a `department`, whether it is critical and its share (0 to 100) of the capital investment as an expected-return target (the capital is SPLIT between the critical departments, so the shares of a batch add up to 100 and are re-balanced when HR skips one, 2026-11-05; `profit_margin_pct` is the proposed estimated margin, migration `7b29ac807c0b`, which also adds `departments.profit_margin_percentage`); for a `position`, `is_critical` with its kind and risk level (a critical position always has both). Copied onto the real department or position on approval. |
| `key_result_ref`, `kpi_weight`, `kpi_target_value`, `kpi_unit`, `kpi_is_inverse` | only for `kpi` (migration `e3de7830b474`): the key result it measures (a ref, optional), its share of the department's KPIs in percent (required for a KPI, CHECK), target, unit, and whether lower is better. A KPI's department is `department_ref` or `department_id`. |
| `ref` | short key other items of the batch use to point here (`D1`, `P3`, `O2`); unique per batch (partial unique index, `WHERE ref IS NOT NULL`) |
| `title`, `rationale`, `sort_order` | what is proposed (a rename's NEW name), why, and the AI's order |
| `department_id`, `position_id`, `reports_to_position_id` | parents/targets that ALREADY exist as real rows (FKs) |
| `department_ref`, `reports_to_ref`, `objective_ref` | parents that are other items of the same batch, not yet real |
| `status` | `pending` / `approved` / `edited` / `rejected` (CHECK) |
| `reviewed_title`, `reviewed_by_user_id`, `reviewed_at` | the decision |
| `created_entity_id` | the real department/position/OKR/key result it became (no FK: it points at four different tables). Cleared again when the item is undone |
| `merge_record` | JSONB, only on a `folded` note made by a merge (migration `d52b8e1f7a39`, 2026-11-11): `{"target_id" or "existing_id", "merged_at", "changes": {item id: {column: OLD value}}}`: the old value of every column the merge changed on any item of the plan. "Undo merge" puts them back exactly. Null on the AI's own notes and on merges made before this column existed (those cannot be undone). Cleared by "add separately" |

A CHECK makes a rename item carry the id it renames. The organogram is `reports_to_position_id` / `reports_to_ref` between positions (the real `positions.reports_to_position_id` is set on approval).

## Cluster 5: KPIs

```sql
CREATE TABLE kpis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    department_id UUID NOT NULL REFERENCES departments(id),
    location_id UUID REFERENCES locations(id),  -- null = department-wide; set = scoped to one location (branch/store model)
    key_result_id UUID REFERENCES key_results(id),
    name TEXT NOT NULL,
    description TEXT,
    weight NUMERIC(5,2) NOT NULL CHECK (weight >= 0 AND weight <= 100),
    is_inverse BOOLEAN NOT NULL DEFAULT FALSE,
    target_value NUMERIC(14,2),
    unit TEXT,
    tracking_mode TEXT NOT NULL DEFAULT 'manual' CHECK (tracking_mode IN ('manual', 'task_count')),
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
- **`description` (added 2026-09-30, during M8 implementation), a free-text field nullable on purpose.** Lets HR explain what a KPI actually means in practice (e.g. what counts as a "closed deal") so employees working toward it understand it, not just see a name and a number.
- **`tracking_mode` decides how this KPI's mid-quarter progress is known, added 2026-09-30 (08_DECISIONS.md).** `'task_count'` means progress is a live count of completed tasks linked to this KPI (`tasks.kpi_id`) within the current period — for a KPI whose target is literally a count of things (e.g. "close 20 deals"), computed on read, nobody enters anything. `'manual'` (the default) means progress is whatever was last typed in via `POST /kpis/{id}/scores` — for a KPI that's a real-world figure this app can't see on its own (revenue, average response time). Deliberately not inferred from whether tasks happen to be linked to the KPI — a task can be linked for reasons unrelated to counting toward the target, so only an explicit choice at KPI-creation time is safe. `task_count`'s live-count read itself depends on the `tasks` table (M10, not built when this column was added) — the column exists now so M10/M12 build against a settled field rather than needing another schema change later.
- **`key_result_id` is nullable on purpose.** Not every KPI needs to trace back to a specific Key Result, some departments have operational KPIs (e.g. "average response time") that support the strategy generally without tying to one measurable OKR target. Making it mandatory would force a fake link where none exists.
- **`kpi_scores` is one row per KPI per scoring period** (a quarter, matching the quarterly dashboard), not a running single value on `kpis` itself. This is what lets the performance dashboard show a trend over time, and it's what the weighted scoring calculation reads from to compute a department's (or location's) overall performance for that period.
- **`score_percentage` is stored, not computed on the fly**, because how "actual vs target" becomes a percentage isn't always a straight ratio (a KPI can be inverse, e.g. lower is better for "customer complaints"). The calculation logic lives once in application code, and the result is written here rather than every dashboard query re-deriving it differently.
- **`kpis.is_inverse` (added 2026-09-30, found missing while implementing the scores upsert) is what actually tells that calculation which formula to use.** The note above always assumed something recorded which KPIs are inverse; nothing did. `FALSE` (default): `score_percentage = actual_value / target_value * 100`. `TRUE`: `score_percentage = target_value / actual_value * 100` — fewer complaints than target scores *over* 100%, more scores under.
- **`kpi_scores` has no `deleted_at`, a deliberate exception to the top-level Conventions rule** that names "performance history" as needing soft delete. This applies once the row's period has actually closed (`period_end` has passed): a scoring record for a closed period is a historical fact, not something that should ever disappear, even softly, and any correction after that point is a new period's record, not hiding or editing the old one. **Before that point — while `period_end` is still in the future — the same row is meant to be updated repeatedly** (`POST /kpis/{id}/scores` upserts it), by `hr_administrator` or `business_executive`, as real-world numbers come in over the course of the quarter, so progress is visible before the period closes, not only after (08_DECISIONS.md 2026-09-29). Same "permanent once closed" reasoning as `workflow_instances` having no `deleted_at`, decided during the 2026-09-04 consistency pass.

```sql
-- AS BUILT 2026-10-22 (M12 slice A, migration c84e1d5d299f, module `scoring`). Constraint names are in the model.
CREATE TABLE employee_kpi_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    kpi_id UUID NOT NULL REFERENCES kpis(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tasks_on_time INTEGER NOT NULL DEFAULT 0,   -- valid tasks done on time (100 each)
    tasks_late INTEGER NOT NULL DEFAULT 0,      -- done late (50 each)
    tasks_not_done INTEGER NOT NULL DEFAULT 0,  -- never done (0 each)
    score_percentage NUMERIC(5,2),              -- 0-100; NULL exactly when the three counts are all 0 ("no data", never 0)
    weight_used NUMERIC(5,2) NOT NULL,          -- the KPI's weight when the row was last written; frozen with the row
    finalized_at TIMESTAMPTZ,                   -- NULL = running figure refreshed nightly; set = frozen at period close
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (employee_id, kpi_id, period_start, period_end)
);

CREATE TABLE department_scores (   -- NEW in M12 (not in the original design), see the note below
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    department_id UUID NOT NULL REFERENCES departments(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    kpi_results_score NUMERIC(6,2),             -- headline: weighted KPI results against target, may exceed 100; NULL when kpis_counted = 0
    kpis_counted INTEGER NOT NULL DEFAULT 0,    -- the N of "N of M"
    kpis_expected INTEGER NOT NULL DEFAULT 0,   -- the M (CHECK counted <= expected)
    punctuality_on_time INTEGER NOT NULL DEFAULT 0,
    punctuality_late INTEGER NOT NULL DEFAULT 0,
    punctuality_not_done INTEGER NOT NULL DEFAULT 0,   -- includes tasks nobody holds
    punctuality_score NUMERIC(5,2),             -- 0-100; NULL when the three counts are all 0
    revenue_allocation_percentage NUMERIC(6,2), -- the department's revenue share when written; frozen with the row
    finalized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (department_id, period_start, period_end)
);

CREATE TABLE executive_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    summary_text TEXT NOT NULL,                 -- CHECK: not blank
    source VARCHAR(10) NOT NULL DEFAULT 'ai',   -- 'ai' (model wrote it, numbers checked) or 'plain' (fact-only fallback)
    facts_fingerprint VARCHAR(64) NOT NULL,     -- hash of the fact sheet; an unchanged hash skips the week's model call
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),   -- when the text was last written (the weekly job replaces it)
    finalized_at TIMESTAMPTZ,                   -- set at period close: frozen
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, period_start, period_end)
);
```

**Built 2026-10-22 (M12 slice A, `08_DECISIONS.md` 2026-10-21 and 2026-10-22), in the NEW module `scoring/` (not folded into `kpis/`, so no studied code changed):** all three tables have RLS `tenant_isolation`, no `deleted_at` (a closed period is permanent history), and CHECK rules that stop "no data" from being stored as a fake zero. **Why `department_scores` was added:** the department headline is built from the KPIs' weights and the company score from each department's revenue share; if a closed quarter were recalculated on read from TODAY's weights and shares, editing a weight in January would silently change Q3's final card. So the result is saved when the row is written, with the revenue share it used, and `employee_kpi_scores.weight_used` does the same for a person's overall score. **How a row is frozen:** `finalized_at` is empty while the period is open (the nightly job refreshes the row) and is set at period close; a row with `finalized_at` set must never be written again. **ENFORCED BY A DATABASE TRIGGER (built 2026-10-22, M12 slice A, migration `c84e1d5d299f`; the user chose to add it):** the function `refuse_change_to_finalized_row()` and a trigger `freeze_finalized_rows` (`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) on each of the three tables refuse any change or delete of a row whose `finalized_at` is already set, with a check-violation error (an `IntegrityError` in the application). Freezing itself (filling `finalized_at` for the first time) is allowed, because the row it replaces is not frozen yet; clearing it again is refused. Tested in `tests/scoring/test_scoring_tables.py` for all three tables, and the test was proven able to fail by dropping a trigger on purpose. To lift the lock for a genuine correction someone must drop the trigger deliberately. The code that writes the rows (slices C and D) will additionally update only rows whose `finalized_at` is empty, so normal flows never hit the lock.

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
    archived_at TIMESTAMPTZ,  -- retired: cannot start new cases, running ones carry on. Added M11 slice A, migration fee24085f70f
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
    completed_at TIMESTAMPTZ,  -- set exactly when status = 'completed' (CHECK check_workflow_instance_completed_at_matches_status)
    cancel_reason TEXT,        -- set exactly when status = 'cancelled' (CHECK check_workflow_instance_cancel_reason_matches_status). Added M11 slice A
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
    completed_at TIMESTAMPTZ,  -- set exactly when status = 'completed' (CHECK check_task_completed_at_matches_status)
    cancel_reason TEXT,        -- set exactly when status = 'cancelled' (CHECK check_task_cancel_reason_matches_status); added M10 slice B, migration c8e41d7a5b92
    blocked_since TIMESTAMPTZ,        -- when the current block started; NULL = not blocked right now. Added M10 slice E, migration f7b2c91d4a60
    approved_blocked_seconds INTEGER NOT NULL DEFAULT 0 CHECK (approved_blocked_seconds >= 0),  -- running total of reviewer-approved blocked time; real deadline = due_at + this. Reset to 0 on reassign. Slice E
    overdue_notified_at TIMESTAMPTZ,  -- when the "task is overdue" notification was sent; NULL = not sent yet. Cleared when due_at changes or the task is reassigned. Added M10 slice D, migration e5a07b3c9d14 (same migration adds the function organizations_with_unannounced_overdue_tasks())
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed','cancelled')),
    created_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE task_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    task_id UUID NOT NULL REFERENCES tasks(id),
    blocked_by_user_id UUID NOT NULL REFERENCES users(id),
    category TEXT NOT NULL CHECK (category IN ('awaiting_approval','awaiting_other_department','external_dependency','other')),
    reason TEXT NOT NULL,
    blocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    unblocked_at TIMESTAMPTZ,  -- null = still blocked
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','rejected')),
    reviewed_by_user_id UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- **Added 2026-11-09 (migration `fb48710b400f`): `workflow_instances.client_value` (DECIMAL(16,2), nullable, CHECK >= 0) and `client_deadline_at` (timestamptz, nullable).** What a job is worth in naira (for example a client's fee) and the date the client expects it done. Whether the figure is at risk, lost or secured is DERIVED when read (`workflow/value.py`), never stored, so it always follows the live overdue state.
- **Built 2026-10-12 (M11 slice A, migration `fee24085f70f`, `08_DECISIONS.md` 2026-10-12).** The three workflow tables as above, each with RLS `tenant_isolation`, plus: `workflow_templates.archived_at` and `workflow_instances.cancel_reason` (not in the original design: archiving and cancel-with-reason were settled 2026-10-12); CHECKs on the instance `status`, on `completed_at`/`cancel_reason` matching the status, on a step's `default_turnaround_hours > 0` (or null) and `step_order >= 1`; indexes `idx_workflow_steps_template_order` and `idx_workflow_instances_template_status` (for "is a case running on this template?"). **`step_order` is deliberately NOT unique in the database**: inserting a step in the middle shifts the later ones and a uniqueness rule would reject that halfway, so the service keeps the numbers sensible. `workflow_instances` has no `deleted_at` and no "current step" column (what comes next is read from the template when a task finishes). The two `tasks` columns `workflow_instance_id` / `workflow_step_id` became real foreign keys, named `fk_tasks_workflow_instance_id` / `fk_tasks_workflow_step_id`; the Task model declares them too (edited with the user's permission) so `alembic check` stays clean.
- **Built 2026-10-09 (M10 slice E, migration `f7b2c91d4a60`, `08_DECISIONS.md` 2026-10-09).** The table as above plus: CHECKs on `category`, `review_status`, `unblocked_at >= blocked_at`, and "reviewed_by/reviewed_at are set exactly when the status is not pending"; a **partial unique index** `uq_task_blocks_one_open_per_task` (one open block per task); RLS `tenant_isolation`. `tasks` gains `blocked_since` and `approved_blocked_seconds`: two stored facts kept in step with the blocks by block/unblock/approve (and reset on reassign), so the overdue rule needs only the task row. Migration `a3d9e61c7b25` updates the cross-tenant lookup function `organizations_with_unannounced_overdue_tasks()` to the same block-aware rule.
- **`task_blocks`, added 2026-09-22 (Jennifer's escalation/accountability submission, see `01_REQUIREMENTS.md` §6a and `08_DECISIONS.md`).** One table serves both the proactive case (an assignee marks a task blocked *before* it goes overdue, `unblocked_at` null while ongoing) and the reactive case (a task went overdue with no block recorded, the Overdue Celery Beat scan prompts, creating this row after the fact). Same `review_status` shape as `ai_suggestions` and membership deactivation, not a new pattern. `due_at` on `tasks` is never touched by this, "currently overdue" and "was this actually late for scoring" both become derived calculations that exclude any *approved* blocked duration, consistent with `due_at` being written once and never rewritten. A `pending` block holds that task out of KPI scoring entirely until reviewed, it is not scored provisionally and corrected later, since a closed period's `kpi_scores` must stay permanent history.
- **One `tasks` table for both workflow-generated and standalone tasks.** `workflow_instance_id`/`workflow_step_id` are nullable so an ad hoc task (a manager just typing "follow up with vendor" with no template behind it) uses the exact same table and the exact same dashboard, rather than needing a second parallel task system.
- **"Overdue" is not a stored status, it's derived: `status IN ('open','in_progress') AND due_at < now()`.** It isn't a state anyone chooses, it's a fact that becomes true the moment the clock passes `due_at` while nobody's touched the status. Storing it as an enum value would mean either a background job flipping it constantly, or it going stale between checks. Computing it at query/read time is simpler and always correct.
- **Late completion is also derived, from history, not stored as a flag: `completed_at > due_at`.** Since both timestamps are just sitting on the row, "was this done on time" is answerable forever, even long after the task is closed, which is exactly what has to feed the performance-scoring calculation later.
- **`due_at` is written onto the task itself when it's created, not read from `workflow_steps.default_turnaround_hours` every time it's displayed.** The turnaround on the step is a template default used once, at creation, to compute a concrete deadline. If someone edits the template's default turnaround afterward, already-created tasks must not silently shift, that would be changing history. *Refined 2026-10-07 (`08_DECISIONS.md`):* this protects against *system* events moving a deadline (a template edit, a task block). An authorized person (creator, department head, HR) may edit `due_at` deliberately, audit-logged with old and new, and **every reassignment must supply a new `due_at`**.
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
    closed_by VARCHAR(20) CHECK (closed_by IN ('employee', 'system')),   -- null while open (2026-10-02)
    close_reason TEXT,                                                    -- why the system closed it; null for an employee clock-out
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((clock_out_at IS NULL AND closed_by IS NULL AND close_reason IS NULL)
        OR (clock_out_at IS NOT NULL AND closed_by IS NOT NULL)),         -- open or fully closed, never half
    CHECK (clock_out_at IS NULL OR clock_out_at >= clock_in_at)
);
-- At most one OPEN record per employee: the database settles simultaneous clock-ins.
CREATE UNIQUE INDEX uq_attendance_one_open_per_employee ON attendance_records (employee_id) WHERE clock_out_at IS NULL;
CREATE INDEX idx_attendance_employee_clock_in ON attendance_records (organization_id, employee_id, clock_in_at);
-- RLS: tenant_isolation policy on organization_id, like every other tenant table.
```

**Design notes:**
- **`closed_by = 'system'` marks a guess.** The nightly auto-close writes the org's midnight cutoff as `clock_out_at`; scoring and payroll later should treat those rows differently from a real employee clock-out. "Unverified" is derived from `closed_by`, not stored as a second flag. Not soft-deletable: a record is a historical fact.
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
