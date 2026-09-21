# Current Task

**M7 — AI Suggestions Engine** (see `09_PROGRESS.md`)

M6 (OKR) backend is merged to `main` (PR #13) and closed out — see
`08_DECISIONS.md` 2026-09-21. M6 frontend is Uche's track, not blocking
this milestone.

**Backend:** `ai_suggestions`, `ai_usage_log` (`04_DATABASE.md` Cluster 4).
Shared internal LLM-calling utility (Claude, per `06_AI_DESIGN.md`),
event-triggered Celery task fired from Org Structure/OKR services. Redis
debounce (`NX EX 60`). Idempotent generation (partial unique index +
`ON CONFLICT DO NOTHING`). ID-hallucination validation against real rows.
`GET /ai-suggestions`, `POST /ai-suggestions/{id}/approve|reject`.

**Also in scope: the scheduled half of the "recurring, not one-time"
requirement.** Event-triggered re-runs (a department marked critical, a new
OKR saved) aren't the only trigger — the Quarterly Objective Review
(`01_REQUIREMENTS.md` §4/workflow #4) is a separate, scheduled trigger: a
Celery Beat job that reads each org's `organizations.fiscal_year_start_month`
(already shipped in M2), scans for orgs whose fiscal quarter just ended, and
re-runs suggestion generation additively.

**Still open — needs a decision before/during the build:**
- **Completeness gap found in review (2026-09-18):** nothing stops the
  exact same suggestion from being regenerated after HR explicitly rejects
  it. The idempotency fix (`08_DECISIONS.md` 2026-09-07) only prevents a
  *duplicate pending* row while one already exists — it says nothing about
  a *rejected* one. Given suggestions regenerate on every OKR/org-structure
  change and again every quarter (the Quarterly Objective Review above), a
  rejected suggestion could resurface repeatedly, indefinitely, training HR
  to ignore the whole review queue. Decide: skip generating a suggestion
  that matches an already-rejected one for the same target (permanently, or
  for some cooldown period), or leave it as-is and accept the
  repeat-nagging risk.

**Depends on:** M2 (`organizations.fiscal_year_start_month`) — done. M4
(Org Structure) — done. M6 (suggestions read department/position/OKR
context — `06_AI_DESIGN.md`'s `missing_department` row specifically reads
existing OKRs as prompt context, a read dependency, not a foreign key) —
done.

## Next recommended action

1. Decide the rejected-suggestion regeneration question above before
   writing the generation code — it shapes the idempotency-index design.
2. Build M7 backend: `ai_suggestions`/`ai_usage_log` models, RLS, the
   shared LLM-calling utility with usage/cost logging (`08_DECISIONS.md`
   2026-09-07), the event-triggered Celery task, the Quarterly Objective
   Review Celery Beat job, and the two endpoints.
3. Standard workflow once done: review → commit → push → PR → merge →
   delete branch → branch `m8-kpis` (or whatever's next per
   `09_PROGRESS.md`).
