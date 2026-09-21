# Current Task


**M4 — Org Structure — backend done and merged to `main` (PR #7). A dropped
follow-up fix has been recovered. M5 — Business DNA is ready to start.**

**Shipped (M4):** `locations`/`departments`/`positions`/`employees` CRUD + RLS,

delete-blocked-while-referenced (departments/positions), employee
offboard/reinstate (cascades to the linked `Membership`, doesn't block on
direct reports), `hr_administrator`-only mutation gating. Full writeup:
`08_DECISIONS.md` 2026-09-20/2026-09-21 entries, `09_PROGRESS.md` M4.

**Also resolved before M4 merged, unblocking M5:** the Business DNA
questionnaire field-list gap that had been open since `01_REQUIREMENTS.md`
was first written — see `08_DECISIONS.md` 2026-09-21. `01_REQUIREMENTS.md`
§1 and `09_PROGRESS.md` M5 both updated with the resolved five-item field
set.

**Process incident, now closed:** a `.gitignore`/provisioning-script fix
committed on `m4-org-structure` after PR #7 had already merged was dropped
from `main` when the old branches were deleted, silently regressing
`.gitignore` and untracking `backend/scripts/db/provision_app_role.sql`.
Recovered via a cherry-pick onto `m4-followup-gitignore-fix`, PR'd and
merged separately. See `08_DECISIONS.md` 2026-09-21 (second entry that
date) for the full account.

## Next recommended action

1. **Standard post-merge cleanup** for both the M4 PR and this follow-up
   fix: `git checkout main && git pull origin main`, delete
   `m4-org-structure` and `m4-followup-gitignore-fix` (local + remote),
   confirm `m5-business-dna` is branched off the now-current `main`.
2. **M5 — Business DNA** is ready to start with its scope settled (no
   open gap left to discover mid-build): `business_dna`,
   `business_dna_core_values` (`04_DATABASE.md` Cluster 3), `GET|PUT
   /business-dna` (upsert), `POST|GET|PATCH|DELETE /business-dna/core-values`.
   Field set: business identity/industry/products & services,
   vision/mission/core values/business model, revenue/operational/customer
   value drivers, performance philosophy/workforce rules, capital
   investment amount. Does not re-ask org structure/job architecture (M4)
   or OKRs (M6).
3. **Frontend, not yet started, both milestones:** M3's notification
   bell/center and M4's Org Structure screens (Departments, Positions,
   Locations, Employee Directory, Offboard/Reinstate) are both open on
   Uche's side — Trello cards exist and are current for both.
