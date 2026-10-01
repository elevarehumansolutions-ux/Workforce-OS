# Current Task

**M8 — Performance: KPI Definitions & Weighting — backend functionally
complete, not yet committed/PR'd/merged.** See `09_PROGRESS.md`'s M8 entry
for what's built; `08_DECISIONS.md`'s 2026-09-29 through 2026-10-01 entries
for the reasoning behind every decision made along the way. Branch:
`m8-kpis`.

## What's left before this milestone closes

1. **Commit, push, PR, merge.** Everything from the design work
   (`tracking_mode`, `is_inverse`, the group-reconcile design) through the
   full implementation (models, migrations, repository, service, router,
   the `kpi_weight` AI chain, `GET /ai-usage`, audit logging, tests) is
   sitting uncommitted on `m8-kpis`.
2. **Tell Uche, non-blocking — doesn't hold up merging this milestone:**
   the group endpoint contract (`PUT /departments/{id}/kpis` — send the
   whole desired KPI list, `id` present = update, absent = create, an
   existing `id` missing from the list = delete; no standalone delete
   endpoint exists). Also worth mentioning: the KPI setup step is a
   natural fit for this same endpoint during onboarding, not mandated,
   his call.
3. Standard workflow once the above are settled: review → commit → push →
   PR → merge → delete branch → branch for whatever's next per
   `09_PROGRESS.md` (M9 — Attendance).

## Not this milestone's job

Frontend: KPI setup per department, the AI-suggested weight split shown in
the same review pattern as M7, and assembling the full onboarding wizard
(Business DNA → Org Setup → OKRs → AI Suggestions for Critical Roles →
KPIs → Invite Team). That's Uche's track. Also not this milestone's job:
`task_count`'s live-progress read and its quarter-end close job (both
need `tasks`, M10) — the design is already written down for whenever that
lands.
