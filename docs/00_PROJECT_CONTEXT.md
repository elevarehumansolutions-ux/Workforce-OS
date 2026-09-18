# Project Context

**Sources:** `Elevare_Workforce_OS_Research_Discovery_Notes.html` (internal discovery notes, Emmanuel) + `ELEVARE WORKFORCE OS Product Document-1.pdf` ("Product Development Phases and PRD Framework", product owner). Note: the PDF states it is a product-direction/onboarding framework, not a final technical spec — a separate "Product Concept Brief v1.0" and a "fuller PRD" are referenced but not yet available in this repo.

## Project Name
Elevare Workforce OS

## Problem
Traditional HR/HCM tools manage administration well but give leadership little visibility into whether business strategy is actually being executed, or which roles/people matter most to outcomes. HR modules (org structure, KPIs, tasks, performance, payroll) tend to be disconnected from each other and from business strategy.

## Product Positioning
An **Enterprise Workforce Execution Platform** — connects business strategy, critical talent, operational execution, AI, and intelligent payroll in one ecosystem. Classified as an **HCM platform with a strategy-execution layer**, explicitly *not* a full ERP (no finance, inventory, procurement) and *not* a conventional HRIS/payroll app.

Core principle (both sources agree): the product must be a **connected system**, not disconnected HR modules:

```
Business DNA → Business Strategy → OKRs → Critical Roles → KPIs →
Employee Responsibilities → Daily Execution → Performance Intelligence →
AI Insights → Payroll → Business Outcomes
```

This pipeline is the backbone of the database schema, not just narrative.

**Corrected 2026-09-02 (stakeholder meeting):** Critical Roles sit between OKRs and KPIs, not after KPIs as originally written. Jennifer was explicit: you cannot generate KPIs for a role before knowing which roles/departments are critical, since KPIs are built around the critical ones. This also fixes the onboarding wizard step order — see `01_REQUIREMENTS.md`.

## Company & Role Context
**Elevare Human Solutions Ltd** — Nigerian company, existing business in HR/recruitment/workforce services. Elevare Workforce OS is a **brand-new, standalone product**, sold alongside (not merged into) Elevare's existing recruitment platform. Scoped from day one as **multi-tenant SaaS for external paying customers**, not an internal tool.

**Clarified 2026-09-02:** Elevare itself has a real internal operations problem, and is using it as the founding case study for this build — Elevare will be **tenant #1** (first customer, testing ground) of the multi-tenant product. This does *not* change the architecture: the product is still built generic/multi-tenant from day one, self-serve onboarding included. It means Elevare's own org structure, departments, KPIs, and workflows become the concrete real-world scenario to validate the generic onboarding flow against — not a special-cased internal tool.

- **Product owner:** Elevare Human Solutions Ltd / HR lead — owns business vision, scope, and HR/business logic.
- **Emmanuel:** Platform manager and technical lead. Background in Python, FastAPI, Django.
- **Team:** 1 backend (Emmanuel) + 1 frontend/UX developer (hired, ~28 Figma screens in progress).

## Users
Five personas per the PRD — resolved 2026-09-02:
- **Employee** — daily execution view
- **Manager** — department-level view: oversees their team's tasks, KPIs, performance
- **HR Administrator** — the primary operator of the system. Not a dashboard viewer like Manager/Executive; runs Business DNA setup, org/employee management, critical-role configuration and approval, workflow admin. This is the persona behind the "auth/onboarding, employee management, critical-role approval" screens already covered in the 28 Figma screens.
- **Business Executive** — org-wide view: oversees performance across all departments and managers
- **System Administrator** — platform-level administration; MVP scope still unconfirmed (likely thin or deferred — no dedicated screens described yet)

## Goal
Prove the central proposition end-to-end for MVP:
```
Business Strategy → Workforce Structure → KPIs → Daily Execution → Performance Visibility
```

## Technology Stack
**Not finalized — Emmanuel's current thinking, open to challenge, not specified in the PRD:**

| Area | Current thinking |
|---|---|
| Shape | Modular monolith (single deployable, internally separated modules) — avoids microservices operational overhead for a 2-person team |
| Backend framework | **FastAPI** — decided 2026-09-02, see `08_DECISIONS.md` |
| Database | PostgreSQL |
| Frontend | React via Next.js, client-rendered only (decoupled SPA — no SSR/Server Components in use, confirmed with Uche 2026-09-18, see `08_DECISIONS.md`) |
| Auth | JWT with role claims (Employee/Manager/HR/Executive/...) |
| Multi-tenancy | **Shared database, shared schema, `organization_id` on every table, enforced by Postgres Row-Level Security** — decided 2026-09-04, see `08_DECISIONS.md` |
| Containerization | Docker from day one |

**Infrastructure:**
- Dev hosting: Railway (or similar) — chosen for low cost pre-launch
- Prod hosting: Azure (tentative), pending conversation with local Microsoft partner (CloudSA), who has also proposed handling security/identity and possibly Azure OpenAI
- Email: Resend (free tier, company subdomain)
- Domain: to be purchased
- Dev tooling: AI-assisted development (Claude/ChatGPT API)

## Engineering Standard (added 2026-09-10)
**"MVP" describes feature scope, not code quality, these are different axes.** MVP means which capabilities ship now versus later phases (see `01_REQUIREMENTS.md` "Explicitly Out of MVP Scope"). It does not mean minimal engineering rigor. Baseline production practice, proper exception handling, pagination on list endpoints, dependency injection, structured error responses, standard dev tooling (Makefile, linting), is expected throughout as ordinary competence, not extra scope requiring its own line item in `09_PROGRESS.md` or Trello to be considered in-scope. Several of these are already specified as conventions in `05_API_DESIGN.md` and `03_ARCHITECTURE.md` (pagination, the error shape, the shared tenant-context dependency); anything not explicitly named should still be assumed to be built to normal production standard unless a doc explicitly says otherwise (the way `07_SECURITY.md` explicitly names what's deliberately deferred). The milestone docs describe *what* ships *when*, not an exhaustive checklist of *how* to write it well, don't wait for permission to write good code. This matters more here than a typical MVP because it's demoed to investors and used for real afterward, but it wouldn't be optional even without that.

## Important Constraints
- **Team size:** 2 people total (1 backend, 1 frontend/UX). Architecture and scope decisions must account for this.
- **AI approach (confirmed, from product owner):** Hybrid — AI suggests, human approves. Nothing auto-activates. MVP AI is **rules/template-based**, not ML — no dataset exists for "which roles are critical per industry" (proprietary business judgment). Manual input limited to Business DNA capture; everywhere else AI assists but requires explicit approve/edit/reject.
- **Dev sequencing:** Emmanuel's original 9-phase sketch (foundation/auth first, strategy/AI-suggestion loop given the most time as core differentiator, payroll last, hardening/launch prep at the end) is **reference input, not the final plan** — it may be missing steps. Treat it as raw material when building the actual task breakdown (destined for Trello) rather than as settled sequencing. Consistent with payroll being Phase 2 Product, not MVP (see below).
- **Known open decisions requiring discussion:** Azure/CloudSA vendor commitment, whether rules-based AI vs pulling RAG forward is still right — see `08_DECISIONS.md` once resolved.
- **Resolved 2026-09-02 (product/scope discussion, see `01_REQUIREMENTS.md` / `08_DECISIONS.md` for detail):**
  - HR Administrator / System Administrator scope clarified — HR Administrator is the operator persona (setup/admin screens), not a fourth dashboard; System Administrator scope still thin/unconfirmed.
  - Critical Role Intelligence MVP scope locked in: classification/tagging only in MVP; vacancy flagging is Phase 2; AI-matched candidate suggestion from the recruitment platform is a Phase 3+ vision item, deliberately not roadmapped yet.
  - Backend framework: FastAPI, not Django.
- **Resolved 2026-09-04:** Multi-tenancy: shared database, shared schema, `organization_id` on every table, enforced by Postgres Row-Level Security (not schema-per-tenant or database-per-tenant). Dedicated-database-per-tenant remains available later as a per-contract enterprise tier, not a default. See `08_DECISIONS.md`.
- **Payroll timeline (updated 2026-09-03):** deferred to Phase 2 per PRD roadmap → reinstated to MVP on 2026-09-02 (believed to be Jennifer's direct instruction) → **reverted to Phase 2 on 2026-09-03** once a follow-up call clarified that the "revenue-allocation" example driving the reinstatement was actually describing OKR/KPI scoring, not a payroll formula. No confirmed MVP payroll requirement exists. See `08_DECISIONS.md`.
- **Resolved 2026-09-03 (follow-up call clarification):** the revenue-target mechanism (capital investment → department allocation → quarterly targets → weighted task scoring → performance dashboards) is confirmed as OKR/KPI generation and Performance Intelligence, **not payroll**. It stays in MVP as part of the existing Business DNA → OKR → Critical Role → KPI pipeline. See `01_REQUIREMENTS.md` §1, §4, §7.
- **Resolved 2026-09-02 (stakeholder meeting with Jennifer, transcript-sourced):**
  - Onboarding sign-up: whoever signs up first becomes the Organization Owner (business owner or HR, either can be first) — not a fixed "HR signs up first" assumption.
  - Company name captured at the Business DNA onboarding step, not at registration (registration is identity-only: name, work email, password).
  - Critical Role model confirmed two-level: **department** gets revenue allocation (e.g. Operations), **position** gets the criticality flag (e.g. General Manager) — criticality attaches to the role, never the person holding it.
  - Objectives added mid-quarter or at quarter-end are additive — they never clear or replace existing KPIs/critical-role suggestions.
  - Shift-based scheduling (Morning/Evening/Night rota) is cut from MVP — Elevare's own case study is a standard office business. MVP attendance is plain clock-in/clock-out. Full shift scheduling is a Phase 3 candidate if Elevare later sells to shift-based industries (retail, healthcare, manufacturing).
  - Microsoft/Entra SSO deferred to Phase 2 (enterprise-tier feature), but auth is built pluggable from day one so it isn't a rearchitecture later.
- **Resolved 2026-09-07:** Billing for MVP is manual (invoice → Paystack/Flutterwave payment link or bank transfer → Elevare staff records it), not automated self-serve subscription billing. Automated billing is explicit Phase 2 scope. See `08_DECISIONS.md`.
- **No open scope conflicts remain, and nothing is blocked on Jennifer as of 2026-09-03.** The earlier "waiting on a payroll worked-example" item is closed — it no longer applies now that payroll is back in Phase 2 and the revenue-allocation mechanism turned out to be unrelated to it.
