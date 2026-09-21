# Current Task

**M4 — Org Structure — backend done, pushed, PR/merge pending**

All M4 backend work is complete, tested (115 tests passing total, 25 new
in `tests/organization/`), and pushed to `m4-org-structure`. Not yet
merged — Emmanuel will open the PR and merge on GitHub as a separate,
later action, not part of this session's flow.

**Shipped:** `locations`/`departments`/`positions`/`employees` CRUD + RLS,
delete-blocked-while-referenced (departments/positions), employee
offboard/reinstate (cascades to the linked `Membership`, doesn't block on
direct reports), `hr_administrator`-only mutation gating. Full writeup:
`08_DECISIONS.md` 2026-09-20/2026-09-21 entries, `09_PROGRESS.md` M4.

**Also resolved this session, unblocking M5:** the Business DNA
questionnaire field-list gap that had been open since `01_REQUIREMENTS.md`
was first written — see `08_DECISIONS.md` 2026-09-21. `01_REQUIREMENTS.md`
§1 and `09_PROGRESS.md` M5 both updated with the resolved five-item field
set.

## Next recommended action

1. **Emmanuel:** open the PR for `m4-org-structure`, review, merge on
   GitHub.
2. **Once merged**, standard post-merge workflow: `git checkout main &&
   git pull origin main`, delete `m4-org-structure` (local + remote),
   branch `m5-business-dna` off the updated `main`.
3. **M5 — Business DNA** is ready to start with its scope settled (no
   open gap left to discover mid-build): `business_dna`,
   `business_dna_core_values` (`04_DATABASE.md` Cluster 3), `GET|PUT
   /business-dna` (upsert), `POST|GET|PATCH|DELETE /business-dna/core-values`.
   Field set: business identity/industry/products & services,
   vision/mission/core values/business model, revenue/operational/customer
   value drivers, performance philosophy/workforce rules, capital
   investment amount. Does not re-ask org structure/job architecture (M4)
   or OKRs (M6).
4. **Frontend, not yet started, both milestones:** M3's notification
   bell/center and M4's Org Structure screens (Departments, Positions,
   Locations, Employee Directory, Offboard/Reinstate) are both open on
   Uche's side — Trello cards exist and are current for both.
