# Current Task

**M6 — OKR** (see `09_PROGRESS.md`)

M5 backend is merged to `main` (PR #10) and closed out — see `08_DECISIONS.md`
2026-09-21. M5 frontend is Uche's track, not blocking this milestone.

**Backend:** `okrs`, `key_results` (`04_DATABASE.md` Cluster 4). CRUD,
`department_id`/`location_id` scoping (null = corporate/dept-wide).

**Still open:**
- **Completeness gap found in review (2026-09-18):** M4 established that a
  department/position can't be deleted while actively referenced (named-
  reason block, `01_REQUIREMENTS.md` §2). No equivalent rule is described
  for deleting an `okr` that still has `kpis.key_result_id` pointing at
  one of its key results — same class of problem (a KPI left pointing at
  nothing coherent), same fix pattern already designed and proven for M4,
  just not yet extended to this milestone. Decide before or during the
  build, not after.

**Depends on:** M4 (`department_id`) — done.

## Next recommended action

1. Build M6 backend: `okrs`/`key_results` models, RLS policies, CRUD
   endpoints, `department_id`/`location_id` scoping, and a decision on the
   delete-blocked-while-referenced gap above.
2. Standard workflow once done: review → commit → push → PR → merge →
   delete branch → branch `m7-ai-suggestions` (or whatever's next per
   `09_PROGRESS.md`).
