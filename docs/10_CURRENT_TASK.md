# Current Task

**M11 — Workflow** (see `09_PROGRESS.md` M11, `01_REQUIREMENTS.md` section 6, `04_DATABASE.md` Cluster 6).

Branch: `m11-workflow` (off `main` after M10's merge). **Nothing is built yet.** Working mode for
this milestone: settle the design questions below *with the user first* (propose and review), then
build in small slices, block by block, as `CLAUDE.md` describes (beginner-to-mid code, never change
code outside the Workflow module without asking, additive wiring only).

## What M11 is

A **generic workflow engine**, not a hardcoded process. Customers (Elevare is just tenant #1) define
their own processes as data:

- **Template:** a name plus an ordered list of **steps**. Started by hand (no other triggers in MVP).
- **Step:** name, **department**, position in the order, optional **default assignee** (a person),
  optional **default turnaround** in hours (used to compute the step task's `due_at`).
- **Instance:** one running case of a template (`subject` = e.g. a client name), with a status
  (`in_progress`, `completed`, `cancelled`).
- **Completing a step's task automatically creates the next step's task.** The chain runs itself.
  The same department may appear in several steps (just two rows).
- **Assignment:** a step with a default assignee puts its task straight on that person; without one
  the task lands with the department (see "what M10 gives you" below), and the head delegates.

Tables are already designed: `workflow_templates`, `workflow_steps`, `workflow_instances`
(`04_DATABASE.md` Cluster 6). Endpoints sketched in `05_API_DESIGN.md` ("Workflow (M11+)"):
template and step CRUD (HR administrator or any `manager`), `POST /workflow-instances`,
`GET /workflow-instances` (filters `status`, `template_id`), `GET /workflow-instances/{id}`.

## What M10 already gives you (don't rebuild)

- `tasks.workflow_instance_id` and `tasks.workflow_step_id` exist as **plain nullable columns with no
  foreign key**. **M11's migration adds the named constraints** (`fk_tasks_workflow_instance_id`,
  `fk_tasks_workflow_step_id`); every existing value is null, so there is nothing to backfill.
- A task with no assignee already works end to end: it sits in the department queue, the head (or HR
  when there is no head) is told, and `POST /tasks/{id}/reassign` (which demands a new `due_at`)
  assigns it. `created_by_user_id` is nullable for exactly this case (a workflow-made task has no
  human creator).
- Overdue, blocks and their review, the overdue scan, the offboarding handover and the clock-in gate
  all apply to a task regardless of how it was created.
- **The rule from the docs: Workflow only ever calls Task's service; Task never calls Workflow.**
  M11 will need a task-creation entry point on `TaskService` that is meant for internal callers
  (no "who may create" check, `created_by_user_id` null). It must not insert into `tasks` directly.

## Design questions to settle before building (not decided yet)

1. **How does completing a task advance the workflow, given Task must not call Workflow?**
   Options: (a) Task exposes a small hook list that Workflow registers into (dependency inversion);
   (b) the complete endpoint calls a thin function that lives in neither module; (c) a Celery sweep
   (like M10's scan) finds completed workflow tasks whose next step hasn't been created, with up to
   10 minutes of delay on every handoff. This is the central architectural decision of the milestone.
2. **Template edits while instances are running** (`09_PROGRESS.md` M11 gap): does an instance keep
   the template as it was when it started (a snapshot / version), or follow later edits? Common
   practice is to snapshot. It decides whether editing a template can shift running deadlines.
3. **Cancelling a running instance** (`workflow_instances.status` has `cancelled`, no endpoint is
   described): who may; what happens to its open task (cancel it through `TaskService`, with a
   reason?); are the later steps simply never created?
4. **Step deadlines:** `due_at` = the moment the task is created plus `default_turnaround_hours`
   (calendar hours, MVP), or no `due_at` when the turnaround is empty? Can whoever delegates
   override it for one instance?
5. **Assignee edge cases at task-creation time:** the default assignee has been offboarded; the
   step's department has no head and no default assignee. (M10's existing behavior: unassigned, head
   or HR notified. Probably reuse.)
6. **Overriding a default assignee for one instance** without changing the saved default
   (`01_REQUIREMENTS.md`: "covering for someone on leave"): at start time, or per step later?
7. **What completes an instance:** completing the last step's task. And a cancelled or abandoned
   mid-chain task (a task cancelled by hand) — does the chain stop, skip, or stay stuck?
8. **Deleting or archiving a template** that has running instances; reordering or removing steps.
9. **Who may start an instance** (anyone? the same people who build templates?) and **who sees
   which instances** (the read scope).
10. **Permissions on template building across departments** (a manager building steps in other
    departments: the docs say no enforced cross-department approval in MVP).

## Not this milestone's job

- Scoring (M12), including how task lateness and blocks feed scores.
- Parallel or conditional steps, other trigger types, a proactive SLA-pause (Phase 2,
  `01_REQUIREMENTS.md` 6 and 6a).
- Frontend (Uche's track): the template builder, "start workflow" and instance progress screens. When
  an endpoint changes what a screen needs, update the Trello board in the same session (`CLAUDE.md`,
  "Frontend impact").

## Deploy items for M10 (the user's, alongside)

Run the six M10 migrations on the VPS in order (`14b29721b95f`, `c8e41d7a5b92`, `e5a07b3c9d14`,
`f7b2c91d4a60`, `a3d9e61c7b25`, `b8e24f6a1c93`), restart the **worker and Beat** containers (a new
task file and schedule), and tell Uche about the three Trello cards. Details in `SESSION_HANDOFF.md`.
