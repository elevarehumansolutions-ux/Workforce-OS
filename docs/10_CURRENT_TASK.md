# Current Task

**Live testing of the staging site, then fixing what it finds.** All twelve milestones that exist (M1 to M12) are
built; M13 (billing) is not. Emmanuel walks the product stage by stage with `15_LIVE_TEST_PLAN.md` and reports
what he sees; each finding is written into `09_PROGRESS.md` (a numbered to-do) and fixed in a small
branch, one commit per item. Working mode: propose first, build when he says so, one small block at a time with a
short explanation (see `CLAUDE.md`).

## Where we are (latest, 2026-11-14 evening)

Emmanuel is live-testing Stage 7 (workflow) with the order in `15_LIVE_TEST_PLAN.md` ("Recommended order"). His
findings were built on branch `live-tests-round3` (to-dos 36 to 39: Start Workflow empty state, one person picker
grouped by department, per-company working hours, turnaround in days). After it is merged and deployed (`alembic
upgrade head` reaches `d5f2b7a93c18`), he finishes Stage 7 step 1 (the template), then goes on: Stage 5, 6, 7 outcomes,
8, 10, Stage 11 steps 1 to 16, and Stage 9 last. We do each step together, one at a time.

## Where we are (2026-11-14, end of day)

PR #69 (`company-restore`) is merged and deployed; Emmanuel live-tested the permanent purge on staging and it
worked. **Next: the rest of the live test** (see "Immediate next action" below), starting with Stage 11 steps 1 to
16 and the phone-width walkthrough. The notes below describe how we got here.

## Where we got to (2026-11-14, earlier)

- **Merged to `main` (PR #68):** the people flow, plan Undo/Redo, multi-company (create, switch), the replaced-head
  windows, the role-change 500 fix, and deleting a company (to-dos 22 to 32). Emmanuel live-tested Stage 2c and
  Stage 11 steps 17 to 28 and they passed.
- **Branch `company-restore` (this work, not merged yet):** to-do 33 (a bin icon on every company you own in
  "Your companies"), to-do 34 ("Deleted companies" with Restore) and to-do 35 (a daily job erases a company for
  good 30 days after it was deleted). Details: `09_PROGRESS.md` to-dos 33 to 35, `08_DECISIONS.md` 2026-11-14.
- After the merge, deploy needs `alembic upgrade head` (reaches `b7d31f9e2c60`) and a restart of the API,
  celery_worker AND celery_beat (a new daily Beat entry), then a hard refresh.

## Immediate next action

1. Run the full backend suite, push `company-restore`, Emmanuel merges and deploys.
2. Emmanuel live-tests Stage 11 steps 29 to 31 (name prefill, delete, restore).
3. He then continues the rest of `15_LIVE_TEST_PLAN.md`: Stage 11 steps 1 to 16 (messages, adding people, plan
   screens, menu and the phone-width walkthrough), and Stages 3 to 10 if not done. Stage 9 uses
   `backend/scripts/admin/stage9_time_helper.py` (`14_PRODUCTION_TROUBLESHOOTING.md` section 12).
4. Each new finding: explain the cause from the code, add it to the numbered to-do in `09_PROGRESS.md`, and build
   it when asked.

## Still open (not built)

- Purge extras (not built): erasing people's own login accounts, a "delete forever now" button, a record that a
  purge happened. (The purge itself is built: to-do 35.)
- Pending-invites list; "what changed" wording in the activity log; no in-app prompt for an existing account with
  an invite waiting; the plan history is shown only in onboarding and the backend does not gate on it; per-card
  Undo is not recorded in the history.
- Merging an already added department or role away (edits the Organization module, needs his approval); workload
  thresholds; a merged role does not re-check "max 3 critical roles per department"; no company-size field;
  payroll provider; a phone-width walkthrough of every screen; server security follow-ups; restoring CI
  (`git revert 53cf5b1`).
