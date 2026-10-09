# Current Task

**M10 — Task**, slice C onward (see `09_PROGRESS.md` M10 and `08_DECISIONS.md` 2026-10-07 and 2026-10-08).

Slices A (create, list, read, edit, complete) and B (cancel, reassign) are built and
tested on branch `m10-tasks`. See `09_PROGRESS.md` M10 ("SLICE A BUILT", "SLICE B BUILT")
and `05_API_DESIGN.md` (### Task (M10)) for the exact contract, and
`docs/SESSION_HANDOFF.md` for the state of the branch (commit/PR status).

**Codebase rule learned in slice B:** anything needed from *before* an atomic
`UPDATE ... RETURNING` (old status, old assignee) must be read before it, because
`populate_existing` refreshes the same ORM object in place.

## Remaining slices, in order

**C. DONE 2026-10-08:** the clock-in gate (uses Attendance's existing `get_open_record`), the
overdue rule in `tasks/overdue.py`, `overdue` on every response and `?overdue=true|false` on the
list, with an agreement test. Nothing left in C. An "is this employee clocked in?" method on
`AttendanceService` (only the repository's `get_open_record` exists today; go through the
service, not a direct `attendance_records` query). The gate applies to the employee's own
task list. `overdue` is derived (`due_at < now` and status open/in progress), never stored;
add `?overdue=true` and an `overdue` field on `TaskResponse`.

**D. DONE 2026-10-08** (see `09_PROGRESS.md` "SLICE D BUILT"). Original description: Overdue scan (Celery Beat). Notify the assignee and the department head when `due_at`
passes; **no head set -> notify the HR administrators** (the fallback from the
department-head decision). Must be idempotent (a retry or late run must not notify twice).

**E. DONE 2026-10-09** (`task_blocks`, block/unblock, the review, blocked time in the overdue
rule, complete/cancel/reassign end a block, the "was something holding up?" prompt; see
`09_PROGRESS.md` "SLICE E BUILT" and `08_DECISIONS.md` 2026-10-09).

**F. DONE 2026-10-09:** `GET /kpis/{kpi_id}/task-progress`, coded in the Task module. The gap that
no API could set `tracking_mode = task_count` was closed with the user's permission (2 lines in
`kpis/schemas.py`). Open KPI-module items, noted only: typed-in scores are not refused for a
task-count KPI; `PATCH /kpis/{id}` with `null` on `name`/`weight`/`is_inverse` is a 500.

**M10 is feature-complete.** Next: push `m10-tasks`, open the PR, merge, run the six migrations on
the VPS, then rewrite this file for the next milestone (M11 Workflow).

## Open questions (settle before the slice that needs them)

All settled on 2026-10-09 (`08_DECISIONS.md`, entry "M10's open questions and the offboarding gap"):

1. **`in_progress`:** deferred. Unused for now; a `POST /tasks/{id}/start` is a small later addition.
2. **Open block on cancel/reassign/complete:** ends it (reassign also resets the approved time). Built.
3. **Assignee must belong to the department:** no, kept as is. Revisit at M12 (noted as an improvement).
4. **Read scope:** kept as is (manager role: own department plus created; executive: read-only,
   sees all). Later refinement: scope managers by reporting line.

**Offboarding handover: BUILT 2026-10-09** as a sweep inside the Task module's scan (no change to
the Organization module, the user's choice): an offboarded employee's open tasks are unassigned,
their open blocks end, and the department head (or HR) is told. Details in the same decision entry.
**The only slice left in M10 is F (the `task_count` live read).**

## Not this milestone's job

Frontend: the daily task list, Assign Task screen, block/unblock UI. That is Uche's track.
When M10's endpoints change what a screen needs, update the Trello board in the same session
(see `CLAUDE.md`, "Frontend impact"). The card for slice A is "[Frontend - Uche] Tasks:
create, list, edit and complete (backend slice A)" (To Do).
