# Journey friction log

Written during the live test (`15_LIVE_TEST_PLAN.md`). Every time Emmanuel hits something manual,
confusing or silent, it goes here, grouped by the person's journey. The point is to design the
automation from real evidence (`08_DECISIONS.md` 2026-11-14 "Nothing is orphaned").

Each entry: what the person had to do by hand, the cause, what was done, and the automation it suggests.
"Fixed" means a screen or rule was changed; the manual effort may still be there (see the last column).

## Principles being tested (agreed 2026-11-14)
1. Defaults beat choices: the system makes the sensible choice, the person only overrides it.
2. Nothing is orphaned: every object has an owner and a place it shows up.
3. One place to look: a single "what needs me today" view.
4. Set-up takes minutes: describe, review, save.

## Journey A: HR administrator sets the company up and builds a workflow

| # | Friction (what was manual or confusing) | Cause | Status | Automation it suggests |
|---|---|---|---|---|
| A1 | "Start Workflow" led to a dead end: no way to create a template from there | Empty state had no next step | Fixed (to-do 36) | Offer "create from a description" right there |
| A2 | The person dropdown showed bare names, so people with similar names could not be told apart | No department or position shown | Fixed (to-do 37: grouped by department, "Name, Position") | Suggest the person from the step's department automatically |
| A3 | Working hours were fixed at 9 to 5; the company works 8 to 5 | Hard-coded | Fixed (to-do 38: per company, set in onboarding and Settings) | Infer from the first week of clock-ins |
| A4 | Turnaround only in hours: "1 day" meant doing the arithmetic | Hours only | Fixed (to-do 39: hours or days) | Suggest turnaround from how long the same step took before |
| A5 | Financial year start was greyed out with "can't be changed yet" | Built read-only, no endpoint | Fixed (to-do 40; also in onboarding) | Ask once in onboarding; default from the country |
| A6 | The Add-step form sat at the bottom of the page and asked for a numeric "Position" | Form below the list; position as a number | Fixed (to-dos 41, 42: window, insert-in-place, drag) | Draft the whole template from a sentence |
| A7 | A step had no way to say which KPI its work counts toward, so workflow work counted for no one's score | No field | Fixed (to-do 46: optional KPI per step) | Suggest the KPI by matching names, person confirms |
| A8 | Template building is step by step by hand, every field | No drafting | OPEN | **Describe the process, system drafts the template (top candidate)** |
| A9 | Some steps need two or more departments to do the work together (for example Legal and Finance both sign off); a step has exactly one department and steps run strictly one after another | Settled MVP decision 2026-10-12: sequential only, one department per step | Fixed (to-do 48, 2026-11-14; Emmanuel approved changing the decision and said all three shapes are valid): extra departments on a step with the rule "everyone" or "the lead decides", and one one-off task assigned to several departments; every department's person is told and emailed | Draft "together" steps from the description (A8) |

## Journey B: department head receives and hands out work

| # | Friction | Cause | Status | Automation it suggests |
|---|---|---|---|---|
| B1 | A task with no named person went nowhere visible; the head saw an empty Tasks page | The "department queue" existed in the rules but no screen showed it | Fixed (to-do 45: "Needs an owner" tab, inline Assign) | Auto-assign (least busy, round-robin) so the head only sees exceptions |
| B2 | Nobody was told a task had arrived: the notification existed but there was no bell | No entry point to Notifications | Fixed (to-do 43: bell with unread count) | A single "Today" page for the role |
| B3 | No email for a new task | No notification ever sent email | Fixed (to-do 44, real delivery untested with fake addresses) | Weekly digest to heads |
| B4 | Handing a task out needs a deadline every time | Rule from 2026-10-07 | Partly eased (keeps the task's own deadline when ahead) | Suggest the deadline |
| B5 | Which tab holds what is not obvious ("My tasks" vs "All tasks I can see") | Two overlapping lists | Partly eased (opens on Needs an owner when non-empty) | "Today" page replaces the tabs |

## Journey C: employee does their day

| # | Friction | Cause | Status | Automation it suggests |
|---|---|---|---|---|
| C1 | After clocking in, "My tasks" can be empty because the task was never assigned to this person | Unassigned work is invisible to members | Eased for heads (B1); members still cannot see or pick up unassigned work | Auto-assign; or "pick up" for members (not decided) |
| C2 | Tasks only appear after clocking in; a person who forgets sees an empty list. Emmanuel (Stage 5): "one could forget to clock in; what about having to clock in first when logging in?" | Attendance gate, nothing prompts at sign-in | Fixed (to-do 47, 2026-11-14): a clock-in prompt window right after sign-in (employees only, on a working day, inside the company's working hours, once per sign-in, "Not now" allowed); NOT a hard block (HR, executives and people with no employee record must still be able to sign in). Optional later: a company setting to clock in automatically at sign-in (rejected for now: attendance would only mean "logged in") | Clock-in prompt at sign-in; reminder when the first task arrives |
| C3 | "Linked KPI: None" with no explanation | Bare text | Fixed (to-do 46: says what it costs) | none |

## Still to examine (not yet walked)
Stage 5 attendance (clock out, midnight auto-close), Stage 6 tasks (overdue, blocked, reassign), Stage 7 outcomes
(At risk, Lost, the money figure), Stage 8 notifications and audit log, Stage 10, Stage 11 (phone width).
Each finding goes into the tables above.
