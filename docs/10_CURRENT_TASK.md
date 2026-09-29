# Current Task

**M8 — Performance: KPI Definitions & Weighting** (see `09_PROGRESS.md`)

M7 (AI Suggestions Engine) is merged to `main` (PR #25, 2026-09-28) and
closed out — see `08_DECISIONS.md`'s 2026-09-22 through 2026-09-28 entries
for the full history, and `.claude/study/M7_STUDY_GUIDE.md` for a
session-by-session study guide if you want to revisit any of it. M8's
frontend (KPI setup screens, the assembled onboarding wizard) is Uche's
track, not blocking this milestone's backend.

## Backend scope

**`kpis` and `kpi_scores`** (`04_DATABASE.md` Cluster 5):
- `POST|GET|PATCH /kpis` (filter: `department_id`, `location_id`). A KPI
  belongs to a department, optionally scoped to one `location_id` (null =
  department-wide); `key_result_id` is nullable — not every KPI traces to
  a specific Key Result.
- **Weight-sums-to-100 validation, app-level, not a database constraint**
  (`kpis.weight` only has a `CHECK (weight BETWEEN 0 AND 100)` per row —
  Postgres has no clean row-level way to check a *group* of rows sums to
  100). Enforce on create and edit within a department/location group;
  **409 on drift**, matching this API's existing conflict-status
  convention (`05_API_DESIGN.md`).
- **Known gap already on record, not to be missed:** the same validation
  needs to re-check the *remaining* KPIs after one is **deleted**, not
  just on create/edit — three KPIs at 30/30/40 losing the 40-weight one
  silently leaves the group at 60%, with nothing prompting a rebalance
  (`09_PROGRESS.md`, flagged 2026-09-18).
- `POST /kpis/{id}/scores` — record a period's actual value; the server
  computes `score_percentage` (stored, not derived on read — the
  actual-vs-target curve isn't always a straight ratio; some KPIs are
  inverse, e.g. lower is better for "customer complaints"). One row per
  KPI per scoring period (a quarter) in `kpi_scores`, which has **no**
  `deleted_at` — a closed period's score is permanent history, a
  correction is a new period's row, not an edit to the old one.
- `GET /kpis/{id}/scores` — historical scores for one KPI.

**`kpi_weight`, the fourth `ai_suggestions.suggestion_type`, reusing M7's
engine.** This is the milestone's main integration work, and M7 was built
in a shape specifically meant to extend cleanly here — study
`ai/generation.py`'s three existing chains (`critical_position`,
`revenue_allocation`, `missing_department`) before designing this one,
since it should mirror whichever of them is the closest analog rather than
inventing new patterns. Needs: the answer schema, the prompt (KPI names +
weights context), a candidate query (which department/location KPI groups
are missing a suggested split, or have one worth re-proposing), the
gather/select/orchestrate trio, wiring into `run_generation`, and a
decision on whether/how it triggers (a KPI created is the obvious event,
matching the "specific event, not every write" pattern already used for
departments/positions/OKRs).

**`GET /ai-usage`** (ships here per `09_PROGRESS.md`; its screen doesn't
land until M13, paired with Billing History — not overlooked, just paired
later). The org's own `ai_usage_log`, `hr_administrator`-only per
`05_API_DESIGN.md`.

## Depends on

M6 (`key_result_id` exists) and M7 (the generation engine `kpi_weight`
reuses) — both done.

## Not this milestone's job

Frontend: KPI setup per department, the AI-suggested weight split shown in
the same review pattern as M7, and assembling the full onboarding wizard
(Business DNA → Org Setup → OKRs → AI Suggestions for Critical Roles →
KPIs → Invite Team). That's Uche's track.
