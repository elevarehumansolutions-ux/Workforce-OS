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

**C. Clock-in gate and derived overdue.** An "is this employee clocked in?" method on
`AttendanceService` (only the repository's `get_open_record` exists today; go through the
service, not a direct `attendance_records` query). The gate applies to the employee's own
task list. `overdue` is derived (`due_at < now` and status open/in progress), never stored;
add `?overdue=true` and an `overdue` field on `TaskResponse`.

**D. Overdue scan (Celery Beat).** Notify the assignee and the department head when `due_at`
passes; **no head set -> notify the HR administrators** (the fallback from the
department-head decision). Must be idempotent (a retry or late run must not notify twice).

**E. `task_blocks`** and `POST /tasks/{id}/block|unblock`, plus approve/reject review
(same shape as `ai_suggestions`). The reactive "why is this late" prompt belongs to D's scan.

**F. `task_count` KPI live-progress read** (08_DECISIONS.md 2026-09-30).

## Open questions (settle before the slice that needs them)

1. Is `in_progress` a separate action (`POST /tasks/{id}/start`) or just the first clock-in /
   unused for now? The status exists; nothing sets it.
2. What happens to an open `task_block` when a task is cancelled or reassigned? (Slice E:
   cancel and reassign now exist and ignore blocks, since none exist yet.)
3. Should an assignee have to belong to the task's department? Slice A only requires "active
   employee of the org". Decide with the user.
4. The `manager` role's read scope was implemented as "its own department plus what it
   created"; confirm that is what the product wants, and what a business executive may do
   beyond reading.

## Not this milestone's job

Frontend: the daily task list, Assign Task screen, block/unblock UI. That is Uche's track.
When M10's endpoints change what a screen needs, update the Trello board in the same session
(see `CLAUDE.md`, "Frontend impact"). The card for slice A is "[Frontend - Uche] Tasks:
create, list, edit and complete (backend slice A)" (To Do).
