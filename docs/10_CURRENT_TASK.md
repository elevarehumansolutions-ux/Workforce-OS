# Current Task

**M10 — Task** (see `09_PROGRESS.md`), after finishing M9's housekeeping.

M9 (Attendance) backend is built and committed on `m9-attendance`, not yet merged.
See `docs/SESSION_HANDOFF.md` for exactly what shipped and `08_DECISIONS.md`'s
2026-10-01 and 2026-10-02 entries for the design trail (including the
prerequisite work it uncovered: login <-> employee linking, email
normalization, reactivation split). `.claude/study/M9_STUDY_GUIDE.md` is the
study guide. M9's frontend is Uche's track, tracked on the Trello board, not
blocking this milestone's backend.

**Housekeeping, do this first:** `git push -u origin m9-attendance`, open the
PR, merge it on GitHub; then `git checkout main && git pull origin main`,
delete `m8-kpis` and `m9-attendance` (local + remote), and branch
`m10-tasks` off the updated `main`.

## Backend scope

**`tasks`** (`04_DATABASE.md` Cluster 6) and **`task_blocks`**, per
`09_PROGRESS.md` M10:
- Standalone task CRUD, `POST /tasks/{id}/complete`, KPI-weight inheritance
  (calls Performance's service, never queries `kpis` directly).
- **Clock-in-gated task list:** the list is only visible once the employee is
  clocked in. Attendance has no "is this employee clocked in?" method on its
  service yet (only the repository's `get_open_record`); M10 will need one, and
  it should go through `AttendanceService`, not a direct `attendance_records`
  query.
- Overdue as derived state, plus a Celery Beat scan that notifies the assignee
  and the **department manager** when `due_at` passes.
- Filters: department, assignee, status, kpi, overdue.
- `task_blocks` and `POST /tasks/{id}/block|unblock`, plus the approve/reject
  review lifecycle (same shape as `ai_suggestions`).
- The live-progress read for `task_count`-tracking KPIs (08_DECISIONS.md 2026-09-30).

## Decisions needed before building (not already settled, talk them through first)

1. **RESOLVED 2026-10-06:** a department's manager is `departments.head_employee_id`, one
   named person set by HR (`08_DECISIONS.md` 2026-10-06). **Built** (2026-10-06, branch
   `m4-followups`, migration `34c5feaf5535`): validation, clearing on offboard, audit, tests.
   **What M10 must still do with it:** when a department has no head, send the alert to the
   HR administrators instead of nowhere. The original gap, for context:
   **"Department manager" was not modelled anywhere** (found 2026-10-02):
   `departments` has no manager/head column, yet the overdue scan and M11's
   workflow routing both need one. Options in `09_PROGRESS.md` M10: an explicit
   `departments.head_employee_id`, derive from the `manager` role in that
   department, or derive from the top position's manager. Needs a product call.
2. **Cancel and reassignment** (gaps flagged 2026-09-18): `tasks.status`
   includes `cancelled` but no endpoint closes a task without counting it as
   completed; nothing describes changing `assigned_to_employee_id` after creation.
3. M9's two parked questions are answered and built (`invite_status` on employee
   responses; `PATCH /memberships` no longer reactivates), see `SESSION_HANDOFF.md`.

## Depends on

M8 (KPI weights) and M9 (clock-in check): both done.

## Not this milestone's job

Frontend: the daily task list, Assign Task screen, block/unblock UI. That is
Uche's track. When M10's endpoints change what a screen needs, update the
Trello board in the same session (see `CLAUDE.md`, "Frontend impact").
