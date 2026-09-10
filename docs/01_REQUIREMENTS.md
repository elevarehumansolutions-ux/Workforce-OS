# Requirements

**Sources:** discovery notes (Emmanuel) + `ELEVARE WORKFORCE OS Product Document-1.pdf` (product owner) + stakeholder meeting transcript 2026-09-02 (Jennifer Otas, Emmanuel Nnabugwu, Uchechukwu Mbonuike) + `Elevare_Journey_Walkthrough.pdf` (frontend design review) + follow-up call transcript 2026-09-03 (Jennifer Otas, Uchechukwu Mbonuike) that clarified the revenue-allocation mechanism. HR Administrator/System Administrator scope and critical-role-intelligence MVP scope resolved 2026-09-02. Payroll scope changed twice: deferred → reinstated to MVP on 2026-09-02 based on a misreading of Jennifer's revenue-allocation example as a payroll bonus formula → **reverted to Phase 2 on 2026-09-03** once the 2026-09-03 call clarified that mechanism is actually OKR/KPI generation and performance scoring, not payroll. See §9 and `08_DECISIONS.md`. No open scope conflicts remain.

## Functional Requirements — MVP

Grouped by the PRD's phase structure. Items marked **(MVP)** appear explicitly in the PRD's MVP roadmap list.

### 1. Business Foundation — Business DNA Engine (MVP)
Capture how the organization operates and creates value:
- Business identity, industry, products & services
- Vision, mission, core values, business model
- Strategic objectives, annual goals, OKRs, business priorities
- Organizational structure, departments, business units, reporting relationships
- Job architecture
- Revenue drivers, operational drivers, customer value drivers
- Performance philosophy, workforce rules
- **Capital investment amount** (added 2026-09-03) — e.g. ₦25,000,000. Feeds the revenue-target generation mechanism described in §4, unrelated to payroll.

> ⚠ **Gap:** discovery notes describe this as a fixed questionnaire covering only "vision, mission, industry, value chain" — materially narrower than the PRD's field list above. The PRD list is used here as the spec since it's the primary source; confirm the actual questionnaire will cover all of it.

### 2. Organization & Workforce Structure (MVP)
- Organization setup, business units, departments, locations
- Reporting structures
- Employee records: job titles, job descriptions, employment info, manager relationships
- User roles and permissions
- **Outcome:** every employee has a defined position in the org structure and reporting hierarchy.

**Deleting a department or position (added 2026-09-07):** blocked, not cascaded, while active references exist, active employees still assigned, open/in-progress tasks tied to it, or a pending AI suggestion about it. The error names what's blocking it (e.g. "5 active employees still assigned"). Once those are cleared, the delete proceeds. Historical references (a completed task, closed KPI scores) are unaffected either way, that's what soft delete already exists to preserve. Caught during the 2026-09-06 gap review as an undefined rule, not a business-rule change, purely about not leaving active work pointing at nothing coherent.

### 3. Strategy-to-Performance Cascade (MVP: OKRs, KPIs)
Flow: Vision → Strategy → OKRs → KPIs → Employee Responsibilities
- Corporate OKRs, departmental OKRs, department KPIs, individual KPIs
- Performance targets, review periods
- Maintain traceable relationships from org objectives down to individual responsibilities

### 4. Critical Role Intelligence (MVP: classification only — locked in, model confirmed 2026-09-02)
Identify positions that are revenue generating, revenue enabling, operationally critical, customer critical, compliance critical, or strategically important.

**Two-level model, confirmed directly by Jennifer:**
- **Department** — gets revenue allocation. Example given: Operations. Marked via a "Critical" toggle at the department level during org setup.
- **Position** — gets the criticality flag. Example given: General Manager. Criticality attaches to the role in the job architecture, never to the person occupying it — if the GM leaves, the position is still critical. AI suggests candidate critical positions from departments already marked critical; HR Administrator approves/edits/rejects.

**AI is restricted to entities that already exist (added 2026-09-04).** The AI must only tag departments and job titles that HR has already created during Organization setup — it must never invent a department or role name that isn't already a real record. This is what keeps suggestions from becoming nonsensical as the org grows.

**Missing-department suggestion — a separate feature from critical-role tagging (added 2026-09-04).** If the AI detects a likely gap (e.g. a business with this kind of OKR typically needs a Sales department, and none exists), it surfaces a distinct, clearly-labeled suggestion with an explicit "Add Department" action — it does not pretend the department already exists or attach criticality to a non-existent record. Only after HR accepts and the department is actually created can it go through normal critical-role tagging like any other department.

**Revenue-target allocation (added 2026-09-03, clarified via follow-up call, see `08_DECISIONS.md`).** Once critical departments are identified, the Business DNA's capital investment amount (§1) is allocated across them as percentages — e.g. 80% to Sales, 50% to Operations, 40% to others. **These percentages can sum to more than 100%**, deliberately: each is an independent expected-return target on the investment, not a slice of a fixed budget. Each department's allocation × the capital investment becomes that department's **annual revenue target**, divided across quarters. This feeds §3 (departmental KPIs) and §7 (performance scoring) below.

**Editing the allocation (added 2026-09-04):** as HR edits each department's percentage, show a running total on screen for their own visibility — not a hard cap, since exceeding 100% overall is intentional. Any validation here (e.g. catching an obviously mistyped value) is a generic engineering safeguard, not a threshold derived from Jennifer's example figures, which were illustrative only, not real numbers to design bounds around.

**This is explicitly not a payroll mechanism.** It generates money-denominated KPI targets for scoring and dashboards only — it does not determine what anyone is paid. See §9 for the (separate, currently Phase 2) question of whether hitting these targets should also affect pay.

Three tiers, locked in:
- **(MVP)** Critical role **configuration/classification** at the position level, scoped to departments already marked critical. Per PRD MVP list ("Critical role configuration").
- **(Deferred — Phase 2 Product)** Critical role **vacancy flagging** — alert when a role already tagged critical becomes vacant. Requires classification to exist first; lines up with the PRD's "Advanced Critical Role Intelligence" in Phase 2.
- **(Vision — Phase 3+, not roadmapped)** AI-matched candidate suggestion from the recruitment platform for vacant critical roles — see `08_DECISIONS.md` and "Explicitly Out of MVP Scope" below.

**Recurring, not one-time:** critical-role suggestions resurface whenever org structure changes or new objectives are added (mid-quarter or at quarter-end), not just once during onboarding. Surfaced via the notification system (see "Notifications," below).

### 5. Daily Workforce Execution (MVP: daily tasks, attendance)
When an employee starts their day, present: daily priorities, tasks, KPIs, deliverables, deadlines, dependencies, progress requirements. Tasks link to employee, department, KPI, and org objective.

### 6. Workflow & Departmental Interdependency (MVP: basic workflow — model designed 2026-09-04)
- Task dependencies, workflow approvals, escalations, handoffs, notifications, status tracking, cross-departmental workflows

> ⚠ **Design gap, now resolved:** discovery notes flagged the Workflow Management screen as "referenced in scope but not yet designed." The model below closes that gap.

**Core principle: this must be a generic engine, not a hardcoded process.** Elevare's own workflows (e.g. its lead-intake process) are not built into the product, they're just the first real data Elevare, as tenant #1, enters into the same generic tool every other customer will use. Nothing about "leads," "recruitment," or Elevare's specific departments may appear in code or fixed logic. Real-world precedent for this pattern: Asana Rules, Jira workflows, Monday.com automations, Salesforce Flow, all generic engines where the vendor builds the mechanism and each customer configures their own process.

**The generic model:**
- **WorkflowTemplate** — a name plus an ordered list of steps. Trigger for MVP is manual: someone starts an instance by hand and enters case-specific details (e.g. a client name). No other trigger types in MVP.
- **WorkflowStep** — belongs to a template, has: a description, a **department**, a **default turnaround time** (used to compute the deadline when this step's task is created), its **position** in the sequence, and an optional **default assignee** (a specific person, not just a department).
- **WorkflowInstance** — one running case of a template, created when someone starts it. Tracks which step is currently active.
- Completing a step's task automatically creates the next step's task. The chain runs itself once started; nobody has to remember to hand off manually.
- **The same department can appear more than once in one template** (e.g. Customer Service logs a complaint at step 1 and follows up at step 4) — this needs no special handling, it's just two rows in the same ordered list.
- **Assignment rule:** if a step has a default assignee set, its task goes straight to that person. If not, the task lands with that department's manager, who delegates to a specific team member. Either way, a task is always ultimately tied to one person once picked up. A default assignee can always be overridden for one specific instance without changing the saved default (e.g. covering for someone on leave).
- **Default assignees exist to remove repetitive manager decisions**, not to replace manager judgment entirely: a department whose incoming step is always handled the same way (e.g. "the same two people, in the same order, every time") should have that saved once, rather than a manager re-deciding it on every single occurrence. A department whose routing genuinely varies (workload-dependent, e.g. "whichever of my 3 people is free") should leave the default blank and keep deciding case by case.
- **Deadlines and lateness:** every task has a `due_at` (computed from the step's default turnaround, or overridden by whoever assigns it) and a `completed_at` (set when marked done). A task still open past its `due_at` flips to **Overdue** and notifies the assignee and the department's manager, even if it isn't finished yet, lateness is surfaced while it's happening, not only judged afterward. The gap between `due_at` and `completed_at` is also the same input that produces the weighted KPI scoring described in §7, this isn't a separate mechanism, it's the same comparison feeding both.
- **Who can build templates:** HR Administrator (org-wide) or any Manager (who may need steps spanning other departments, in which case they're expected to have already confirmed realistic turnaround times with those departments' managers, the same coordination that would happen with no software involved — the tool doesn't enforce a cross-department approval step for this in MVP, that would be solving a people problem with unnecessary engineering).

### 7. Performance Intelligence (MVP: basic performance tracking)
- Employee performance, KPI achievement, task completion, quality indicators
- Manager assessments, performance reviews
- Employee Impact Score — **Phase 2 Product**, not MVP basic tracking
- Department performance, executive performance dashboards
- Platform must distinguish activity vs. completion vs. performance vs. business impact

**Weighted KPI-to-target scoring (added 2026-09-03, mechanism corrected 2026-09-04).** Weight lives on the **KPI**, not on individual tasks. Each KPI within a department gets a weight (e.g. "Lead Response Time" = 30%, "Deal Closure Rate" = 70%), weights sum to 100% within a department. AI suggests a starting split when KPIs are set up, HR approves/edits — same pattern used everywhere else. When a manager assigns a task and links it to a KPI (already how the Assign Task screen works), that task automatically inherits the linked KPI's weight — the manager never picks or thinks about a weight directly. A KPI's own scoring curve reflects execution quality, not just completion — Jennifer's example: closing a lead within 5–7 days scores well, faster scores higher, slower scores lower. Weighted KPI scores roll up to show whether an employee/department is tracking toward its department's quarterly revenue target (§4), visualized as a trend graph (up = on track, down = falling behind). This is scoring/visualization only, feeding dashboards, not payroll.

### 8. AI Workforce Intelligence (MVP — confirmed scope & approach)
**Confirmed by product owner (both sources agree) — the actual business requirement, implementation-agnostic:**
- AI is an intelligence/recommendation layer, not an autonomous decision-maker
- Human approval required for all consequential decisions (approve/edit/reject — nothing auto-activates)
- MVP AI surfaces: Critical Role suggestions, KPI suggestions
- Approvals/corrections become future training data once enough organizations have gone through the loop (no proprietary "critical roles per industry" dataset exists yet, this is how one gets built over time)
- Future (Phase 2/3): workforce insights, performance patterns, workload analysis, productivity trends, succession recommendations, workforce optimization, organizational risk alerts

**Implementation approach (Emmanuel's technical call, revised 2026-09-05, see `08_DECISIONS.md`):** suggestions are generated by calling an LLM (Claude/GPT/Azure OpenAI, provider TBD) with the org's existing department/position/industry context, not by matching against a hand-written table of title patterns per industry. A hand-curated rules table would have required someone, most likely Jennifer, to author and maintain critical-role patterns for every industry this product might ever sell into, not a reasonable ask, and not necessary since a pre-trained LLM needs no such dataset. This is an implementation detail, not a change to the product requirement above; it does not need product-owner sign-off.

> ⚠ **Design gap:** discovery notes confirm the AI-suggestion/approval UI pattern is designed for Critical Roles but **not yet replicated for KPI Suggestions**.

### 9. Intelligent Payroll — **Phase 2 Product, not MVP** (reverted 2026-09-03)

**History, for the record:** originally scoped to Phase 2 per the PRD roadmap → reinstated to MVP on 2026-09-02 after the stakeholder meeting, on the belief that Jennifer's revenue-allocation example ("40% allocated, 120% achieved, ×3") was describing a payroll bonus formula → **reverted back to Phase 2 on 2026-09-03** once a follow-up call clarified that mechanism is actually the OKR/KPI revenue-target and scoring system described in §4 and §7, unrelated to what anyone is paid. No confirmed MVP payroll requirement exists. Emmanuel confirmed no further clarification is needed from Jennifer on this point.

The content below is kept as sourced reference material for when payroll is built in Phase 2 — the Nigerian statutory rates and architecture principles remain valid, only the timing changed.

Payroll is two separate layers, not one feature:

**Layer A — Standard payroll (well-understood, buildable now).** Base salary, statutory deductions, attendance adjustments, leave adjustments, net pay. Runs for every employee regardless of role.

Nigerian statutory rules for this layer (sourced 2026-09-02, needs accountant sign-off before first real run — do not treat as final):
- **PAYE** (Nigeria Tax Act 2025, effective 1 Jan 2026): 0% to ₦800,000; 15% on next ₦2.2M (to ₦3M); 18% on next ₦9M (to ₦12M); 21% on next ₦13M (to ₦25M); 23% on next ₦25M (to ₦50M); 25% above ₦50M. Annual chargeable income.
- **Reliefs:** Consolidated Relief Allowance is **abolished**. Replaced by rent relief — 20% of annual rent paid, capped at ₦500,000, tenants only, requires documentary evidence (receipt/transfer record/lease). Product implication: need a place for employees to declare and evidence rent.
- **Pension** (Pension Reform Act 2014): employee 8% minimum, employer 10% minimum, on Basic + Housing + Transport.
- **NHF:** 2.5% of basic salary (employee).
- **NSITF:** 1% of total gross monthly payroll (employer only, no employee deduction).
- **Edge case to confirm with an accountant:** minimum-wage earners (₦70,000/month = ₦840,000/year) are PAYE-exempt by a separate provision, which sits just above the ₦800,000 zero-band threshold — confirm how the two interact.
- All of the above must be modeled as **effective-dated configuration data** (rates/bands with `effective_from`), not hardcoded — the Jan 2026 change would otherwise have required a code deploy instead of a data update.

**Layer B — Incentive/bonus pay.** Status as of 2026-09-03: **not a confirmed requirement.** The three-selectable-models proposal (fixed amount per outcome, percentage of value generated, target-based bonus) was built on the same misreading as the MVP-reinstatement decision above — it assumed Jennifer's revenue-allocation example was a payroll formula. It wasn't. Whether hitting a department's revenue target (§4) should *also* change what an individual is paid remains genuinely unanswered and unconfirmed — kept here only as a reminder that the question exists, not as scoped work. Revisit if/when payroll is picked up in Phase 2.

**Payroll architecture principles (apply to both layers):**
- **Immutable payroll runs** — a run is a frozen snapshot; corrections happen in the next run, never by editing history.
- **Effective-dated rates** — statutory and org-specific rates carry `effective_from`/`effective_to`; a run always calculates against the rates in force at that time.
- **Decimal arithmetic only** — no floats for money.
- **Draft → review → approve → commit → lock** workflow, matching the design already in the Journey Walkthrough deck (Payroll Hub → Pay Cycle List → Review & Approve, final approval flagged irreversible).
- **Calculation is separate from disbursement.** MVP produces the payroll register and a bank-ready payment file; the company executes payment through its own bank or a transfer API (e.g. Paystack/Flutterwave). Actually moving money is out of scope — that's a money-transmission problem, not a payroll problem.
- **Revenue-conversion (Layer B) resolves before statutory deductions (Layer A)** — a bonus changes gross earnings, which changes tax owed that month.

**Sequencing note:** payroll consumes KPI/attendance/leave data, so whenever it is built (Phase 2), it comes after the Business DNA → OKR → Critical Role → KPI → daily execution loop is running and producing that data.

### 10. Leave Management — **Phase 2 Product, not MVP** (reverted 2026-09-04)

**History, for the record:** originally implied only inside dashboard notes → promoted to its own explicit MVP module on 2026-09-02, per Jennifer's direct instruction in that day's stakeholder meeting → **moved to Phase 2 on 2026-09-04**, a scope call by Emmanuel to keep MVP focused on the Business DNA → OKR → Critical Role → KPI → daily execution loop. **Not yet confirmed with Jennifer** — she explicitly asked for this in MVP, so this reversal needs to go to her the same way the payroll reversal did, it isn't settled just because Emmanuel proposed it here.

The content below is kept as the design already worked out, for whenever this is picked up in Phase 2 — only the timing changed, not the requirement itself.

Request → manager approval → balance deduction.
- Leave types: Annual, Maternity, Sick, Compassionate, Study, Casual (per Journey Walkthrough deck) — configurable leave-policy list, org-specific day allowances (e.g. 10–20 working days depending on org).
- Employee: submit request, view balance (days remaining per type, e.g. 15/21 annual).
- Manager: approve/reject requests for their department; approvals populate the manager dashboard's pending-approvals widget and the notification stream.
- Leave data feeds Attendance ("On Leave" status) and, once payroll is built in Phase 2, Payroll's leave adjustment.

### 11. Executive Business Intelligence (MVP: basic reporting)
Executive dashboards should eventually cover: workforce health, critical roles, department performance, KPI achievement, operational bottlenecks, workforce productivity, employee impact, revenue-related workforce indicators, payroll trends, workforce risks, AI-generated insights. MVP scope is "basic reporting" only — full dashboard breadth is a later-phase target.

**Corrected 2026-09-02 (Jennifer, confirmed via Journey Walkthrough deck review):**
- Trend view **defaults to quarterly** (Q1–Q4, matching how businesses actually operate), not six-month — plus a **custom date range picker** for arbitrary periods.
- Clicking a department in the departmental breakdown must **drill down to every individual employee in that department**, showing how each person's performance rolls up into the department's overall score. A summary-only table with no click-through is not sufficient.

> Design-review note (2026-09-02): the Journey Walkthrough deck still shows a six-month trend with no drill-down — flagged to the frontend dev as a fix, not yet built.

**Added 2026-09-07 (Emmanuel, informed by this MVP being investor/public-facing, not committed with Jennifer yet):**
- **Employee leaderboard** — surfaces "high performing employees," closes a gap where the drill-down requirement above was documented but never actually modeled at the individual-employee level (see `04_DATABASE.md`, `employee_kpi_scores`).
- **Company Performance Score** — a single headline number on the executive dashboard, an aggregate of all departments' scores.
- **Most Improved** employee/department — biggest quarter-over-quarter score improvement.
- **AI-generated executive summary** — a short LLM-generated narrative of a period's performance, reusing the LLM integration built for AI Suggestions (`06_AI_DESIGN.md`).

These are additive, don't reverse or conflict with anything Jennifer has confirmed, but worth telling her and Uche about as a courtesy, same as any other product-visible addition, rather than treating it as silently decided.

### 12. Notifications (cross-cutting, all roles)
- Reachable from every role via a bell icon; centralizes AI-suggestion alerts, approval requests, and system messages, filterable by category.
- **Role-specific streams:** Employee, Manager, HR, and Executive each see notifications relevant to their role, not one shared feed. (Status as of 2026-09-02: unconfirmed whether the single Notifications page already filters by role under the hood, or still needs to — flagged to frontend dev.)
- Critical-role and KPI suggestions resurface here whenever org structure changes or objectives are added — this is the recurring mechanism referenced in §4 and the Quarterly Objective Review workflow below.

## Non-Functional Requirements
- **Multi-tenant SaaS** for external paying customers (not internal-first) — isolation model TBD (leaning shared-schema + `organization_id` + RLS, unvalidated against real payroll data)
- Role-based access control across Employee / Manager / HR Administrator / Business Executive / System Administrator
- Scalable enterprise SaaS architecture (PRD explicit requirement, stated repeatedly per phase)
- Data retention/compliance implications for payroll — "validated against applicable employment and payroll requirements" (PRD, Phase 9) — Nigeria confirmed as the operating jurisdiction; see §9 for sourced statutory rates
- **Onboarding/signup (corrected 2026-09-02):** whoever signs up first becomes the Organization Owner — business owner or HR, either can be first. Identity (User) is separate from org role (Membership); the Owner assigns HR Administrator/Manager/Executive/Employee to invited teammates. Registration form is identity-only (name, work email, password) — company name is captured at the first onboarding step (Business DNA), not at registration.
- **Auth provider pluggable from day one** — email/password for MVP; Microsoft/Entra SSO deferred to Phase 2 (per-tenant OIDC/SAML, likely an enterprise-tier feature) but the user model must not hardcode password-only assumptions now.
- **Attendance is plain clock-in/clock-out** — no shift scheduling (Morning/Evening/Night rota, shift swaps, coverage rules) in MVP. Elevare's own case study is a standard office business. Full shift scheduling is a Phase 3 candidate if the product later sells to shift-based industries.

## User Roles
Per PRD, resolved 2026-09-02:
- **Employee** — daily execution, tasks, KPIs, attendance
- **Manager** — department-level oversight: their team's tasks, KPIs, approvals, assessments
- **HR Administrator** — the system operator, not a dashboard-viewer role. Runs Business DNA setup, org/employee management, critical-role configuration and approval, workflow admin. Covered by the existing "auth/onboarding, employee management, critical-role approval" Figma screens — no separate dashboard needed.
- **Business Executive** — org-wide oversight: performance across all departments and managers
- **System Administrator** — platform-level administration; MVP scope still thin/unconfirmed, no dedicated screens described yet

## Main Workflows
1. **Onboarding (corrected 2026-09-02):** Sign up (business owner or HR, first one in becomes Org Owner) → **Business DNA** → **Organization setup** (departments incl. Critical toggle, locations, reporting hierarchy) → **OKRs** (corporate + departmental objectives/key results) → **AI Suggestions for Critical Roles** (positions within critical departments, human approves/edits/rejects) → **KPIs** (departmental KPIs assigned to the now-identified critical roles/departments) → **Invite Team**. Critical Roles sit between OKRs and KPIs — this is a correction to the original wizard order, which had OKRs+KPIs bundled before AI Suggestions.
2. **Strategy cascade:** Corporate OKRs set → Critical Role Engine identifies critical departments/positions → departmental/individual KPIs assigned to those roles → cascades to employee responsibilities.
3. **Critical role identification:** AI suggests critical positions (within departments already marked critical) from Business DNA + org data → HR Administrator reviews/approves/edits/rejects. Recurs on org changes or new objectives, not one-time.
4. **Quarterly Objective Review (new, 2026-09-02):** At each quarter's end (per the org's configured fiscal year), objectives are reviewed/adjusted; Executive/HR can also add objectives mid-quarter. Either trigger re-runs critical-role/KPI suggestions — **additively**, appending to existing objectives/KPIs, never clearing or replacing them.
5. **Daily execution:** Employee clocks in → task list becomes visible (never shown before clock-in) → sees daily tasks/KPIs/deadlines, sortable by priority (High → Medium → Low) → completes/updates progress.
6. **Cross-department workflow:** Task completed in one department triggers dependent action/approval in another → escalation/notification if blocked.
7. **Leave request cycle (Phase 2, not MVP — moved 2026-09-04, pending confirmation with Jennifer):** Employee submits leave request → Manager approves/rejects → balance deducted → reflected in Attendance ("On Leave") and Payroll, once built. See §10.
8. **Performance review cycle:** KPI achievement + manager assessment → performance record → visible on manager/executive dashboards.
9. **Payroll (Phase 2, not MVP — reverted 2026-09-03):** approved attendance + leave data → Layer A (statutory) calculation → draft → review → approve (irreversible) → payroll register + payment file, once built. See §9.
9a. **Revenue-target scoring cascade (MVP, added 2026-09-03):** Business DNA capital investment → allocated across critical departments as revenue-target percentages → annual target split by quarter → individual task/KPI weighted scores roll up against the department's quarterly target → visualized as a trend graph on manager/executive dashboards. See §4 and §7. This is scoring/visualization only, not payroll.
10. **Executive oversight:** Executive dashboard aggregates workforce health, critical roles, KPI achievement, bottlenecks, quarterly trend (with custom date range), department drill-down to individual employees, and (future) AI-generated risk insights.
11. **Manager-initiated employee onboarding:** Manager adds/invites an employee directly to their own department via the Employees module, without routing through the Org Owner.

## Explicitly Out of MVP Scope (Phase 2 / Phase 3 Product, per PRD)
- **Intelligent Payroll (both layers)** — reverted to Phase 2 on 2026-09-03, see §9 and `08_DECISIONS.md`
- **Leave Management** — moved to Phase 2 on 2026-09-04, pending confirmation with Jennifer (she requested it for MVP on 2026-09-02), see §10 and `08_DECISIONS.md`
- Advanced Critical Role Intelligence (incl. critical-role vacancy flagging), Employee Impact Score, advanced performance management, AI recommendations (beyond Critical Role/KPI suggestions), advanced workflows, Revenue Impact Dashboard, advanced analytics, workforce planning *(Phase 2)*
- Advanced AI workforce intelligence, predictive analytics, recruitment integration, learning & development, succession planning, enterprise integrations, mobile apps, multi-country payroll, industry-specific configs, advanced executive intelligence, **full shift-based scheduling** *(Phase 3)*

**Phase 3+ vision item (not yet roadmapped):** AI-matched candidate suggestion for vacant critical roles, pulled from Elevare's existing recruitment platform's AI Talent Match engine, in place of running job ads. Proposed by Emmanuel, deliberately deferred — depends on critical-role classification (above) and a cross-product integration between Workforce OS and the recruitment platform that hasn't been designed. See `08_DECISIONS.md`.
