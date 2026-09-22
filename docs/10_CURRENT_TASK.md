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

**Resolved (2026-09-22):** the rejected-suggestion regeneration question
flagged in the 2026-09-18 review is settled — see `08_DECISIONS.md`
2026-09-22. A rejected suggestion (same target, same `suggestion_type`) is
suppressed from regenerating until the next Quarterly Objective Review for
that org, not permanently and not on a fixed-duration cooldown. This needs
to be designed into the idempotency logic (alongside the existing
pending-duplicate index, `08_DECISIONS.md` 2026-09-07) from the start, not
added after the generation code is written.

**Depends on:** M2 (`organizations.fiscal_year_start_month`) — done. M4
(Org Structure) — done. M6 (suggestions read department/position/OKR
context — `06_AI_DESIGN.md`'s `missing_department` row specifically reads
existing OKRs as prompt context, a read dependency, not a foreign key) —
done.

## Next recommended action

1. Build M7 backend: `ai_suggestions`/`ai_usage_log` models, RLS, the
   shared LLM-calling utility with usage/cost logging (`08_DECISIONS.md`
   2026-09-07), the event-triggered Celery task, the Quarterly Objective
   Review Celery Beat job, and the two endpoints — idempotency design
   incorporates both the pending-duplicate index (2026-09-07) and the
   rejected-suggestion quarterly-cooldown suppression (2026-09-22) from
   the start.
2. Standard workflow once done: review → commit → push → PR → merge →
   delete branch → branch `m8-kpis` (or whatever's next per
   `09_PROGRESS.md`).
