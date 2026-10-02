# Current Task

**M9 — Attendance** (see `09_PROGRESS.md`)

M8 (Performance: KPI Definitions & Weighting) is merged to `main` (PR #27,
2026-10-01) and closed out — see `08_DECISIONS.md`'s 2026-09-29 through
2026-10-01 entries for the full design and implementation trail (note:
PR #26 merged first, but only the design-phase commits; PR #27 carries
the actual backend — both entries are there, read the last one first if
short on time), and `.claude/study/M8_STUDY_GUIDE.md` for a session-by-
session study guide if you want to revisit any of it. M9's frontend (the
clock-in/out widget, removing the old shift-scheduling grid) is Uche's
track, not blocking this milestone's backend.

**Housekeeping still open from M8, do this first:** `m8-kpis` has not
been deleted yet, local or remote. `git checkout main && git pull origin
main`, delete `m8-kpis` both places, then branch `m9-attendance` off the
updated `main`.

## Backend scope

**`attendance_records`** (`04_DATABASE.md` Cluster 7):
- `POST /attendance/clock-in`, `POST /attendance/clock-out`.
- `GET /attendance` — an employee's own history (filter by date range).
- **"Currently clocked in" is derived, not stored**: `clock_out_at IS
  NULL` on the employee's most recent record. No separate status flag.

**Needs a decision before building, not already settled — talk it
through first, same working mode as M8:** what happens if someone clocks
in and never clocks out (forgets, the tab closes, whatever)? Since
"currently clocked in" is derived from `clock_out_at IS NULL`, an
unclosed record just stays open indefinitely — silently still "clocked
in" the next day, or the next week. Real options, none chosen yet:
- Block a new clock-in while one is still open (force resolving the
  stale one first — but resolving it *how*, and by whom?).
- Auto-close at some cutoff (end of day? a fixed number of hours?) —
  needs a real number, not an arbitrary one.
- Allow a new clock-in regardless, leaving the old one open forever as
  a visible anomaly someone has to notice and fix manually.

Separately, but worth deciding in the same conversation: should clocking
in while already clocked in (without clocking out first) be explicitly
rejected with a real error, or does today's design already prevent it by
construction? Confirm rather than assume.

## Depends on

M4 (`employee_id` exists) — done.

## Not this milestone's job

Frontend: the clock-in/out widget, and removing the old Morning/Evening/
Night shift-scheduling grid from the Journey Walkthrough deck (MVP
attendance is plain clock-in/clock-out only, `08_DECISIONS.md`
2026-09-02). That's Uche's track.
