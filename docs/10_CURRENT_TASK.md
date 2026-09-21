# Current Task

**M5 — Business DNA — backend done and merged to `main` (PR #10). Ready to
pick either M5 frontend or M6 backend next.**

**Shipped:** `business_dna`/`business_dna_core_values` models + RLS,
repository, service (upsert with `organization_name` write-through and
`SAVEPOINT`-based race recovery), router (`GET|PUT /business-dna`,
`POST|GET|PATCH|DELETE /business-dna/core-values`), 11 new tests. Full
writeup: `08_DECISIONS.md` 2026-09-21 entries (field list, access
model/upsert logic, ruff/docstring pass, the duplicate-exception fix, the
M5-done entry), `09_PROGRESS.md` M5.

**Also merged in the same PR:** a full-backend ruff/docstring compliance
pass (`08_DECISIONS.md` 2026-09-21, "Ruff docstring compliance pass") —
`backend/pyproject.toml` added, every `.py` file under `backend/app/`,
`backend/alembic/`, `backend/tests/` brought to zero ruff errors.

**Also resolved earlier this session:** the `.gitignore`/provisioning-
script fix PR #7 had dropped is merged too (PR #9,
`m4-followup-gitignore-fix`) — `backend/scripts/db/provision_app_role.sql`
and the env templates are tracked again.

## Next recommended action

1. **Standard post-merge cleanup:** delete `m5-business-dna`,
   `m4-followup-gitignore-fix`, `m4-org-structure` (local + remote) if not
   already done — confirm current work branches off the now-current
   `main`.
2. Two independent next steps, both unblocked:
   - **M5 frontend:** Business DNA onboarding step (five-item field set,
     `09_PROGRESS.md` M5) — Uche's track, not started.
   - **M6 backend:** OKR (`okrs`, `key_results`, Cluster 4) —
     `09_PROGRESS.md` M6. Has one known completeness gap already flagged
     (no delete-blocked-while-referenced rule for an `okr` still pointed
     at by `kpis.key_result_id`) — worth deciding before or during that
     build, not after.
3. **Frontend, not yet started, multiple milestones:** M3's notification
   bell/center and M4's Org Structure screens are both still open on
   Uche's side — Trello cards exist and are current for both.
