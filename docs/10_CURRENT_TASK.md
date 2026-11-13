# Current Task

**Live testing of the staging site, then fixing what it finds.** All twelve milestones that exist (M1 to M12) are
built; M13 (billing) is not. Emmanuel walks the product stage by stage with `15_LIVE_TEST_PLAN.md` and reports
what he sees; each finding is written into `09_PROGRESS.md` (a numbered to-do) and fixed in a small
branch, one commit per item. Working mode: propose first, build when he says so, one small block at a time with a
short explanation (see `CLAUDE.md`).

## Where we are (2026-11-13)

Branch `people-flow` (off `main` after PR #64) holds the "one front door for adding a person" work: activity lines
that name what was acted on, the optional invite name, "Make head of department" on Add Employee, an org chart in
the Employees section, logins without employee records, and multi-company (invite an existing account, accept with
its password, switch company). Committed, not pushed. Deploy needs `alembic upgrade head` (`e7a41c9b3d26`).
Emmanuel tests it through Stage 11 D2 of `15_LIVE_TEST_PLAN.md`. Details: `09_PROGRESS.md` "DONE 2026-11-13".

## Earlier (2026-11-11)

- Branch `ux-fixes-live-testing` holds every fix from the live test so far (frontend: validation messages, manager
  dropdown and "Vacant" roles, "Save and add another", department heads, phone menu, My profile and Sign out;
  backend: audit names, Undo on Added, Undo merge, skip cascade, quarter-start KPI-weight reminder, automatic
  reporting manager, the Stage 9 time helper). It is **not pushed and not merged**; nothing was seen in a browser.
  The exact list is in `09_PROGRESS.md` "DONE 2026-11-11".
- Deploying it needs `alembic upgrade head` (migration `d52b8e1f7a39`) and a restart of the API and the Celery
  worker/beat.

## Immediate next action

1. Push the branch, open the PR, merge, deploy (above).
2. Emmanuel continues the live test: Stage 2c (undo and merge undo), Stage 3 (people, automatic managers, shared
   roles), Stage 4 onward. Stage 9 uses `backend/scripts/admin/stage9_time_helper.py`
   (`14_PRODUCTION_TROUBLESHOOTING.md` section 12).
3. Each new finding: explain the cause from the code, add it to the numbered to-do in `09_PROGRESS.md`, and build
   it when asked.

## Still open (not built)

Merging an already added department or role away (edits the Organization module, needs his approval); workload
thresholds; a merged role does not re-check "max 3 critical roles per department"; no company-size field; payroll
provider; a phone-width walkthrough of every screen; server security follow-ups; restoring CI
(`git revert 53cf5b1`).
