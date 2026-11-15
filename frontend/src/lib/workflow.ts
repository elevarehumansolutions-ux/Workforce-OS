import { apiFetch } from "@/lib/api";
import { isHr } from "@/lib/tasks";
import type { CallerContext, TaskStatus } from "@/lib/tasks";

export interface WorkflowTemplate {
  id: string;
  organization_id: string;
  // The department that OWNS the template (steps can belong to other departments).
  department_id: string;
  name: string;
  created_by_user_id: string | null;
  // null = usable
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStep {
  id: string;
  workflow_template_id: string;
  step_order: number;
  name: string;
  department_id: string;
  // null = nobody is named: the task goes to the department's head (else HR), who hands it out
  default_assignee_employee_id: string | null;
  // The turnaround is given in hours OR in working days (never both); both null = no deadline.
  // Counted in the company's working hours (Settings > Working hours); one day is a full working day.
  default_turnaround_hours: number | null;
  default_turnaround_days: number | null;
  // The KPI the step's tasks count toward (a KPI of the step's department); null = not linked, so the
  // tasks do not count in performance scores.
  kpi_id: string | null;
  // Other departments that do this step TOGETHER with `department_id` (empty = an ordinary one-department
  // step). Each gets a task of its own when the step starts.
  participants: StepParticipant[];
  // With participants: "all" = the case moves on when every department has finished; "lead" = only
  // `department_id`'s task counts and the others are helpers.
  completion_rule: CompletionRule;
  created_at: string;
  updated_at: string;
}

export type CompletionRule = "all" | "lead";

export interface StepParticipant {
  id: string;
  department_id: string;
  default_assignee_employee_id: string | null;
  kpi_id: string | null;
}

// What the step form sends for one extra department (no id: the list is replaced as a whole).
export interface ParticipantDraft {
  department_id: string;
  default_assignee_employee_id: string;
  kpi_id: string;
}

export type CaseStatus = "in_progress" | "completed" | "cancelled";

// A "case" is one running run of a template, e.g. "Client Onboarding" for "Zenith Ltd".
export interface WorkflowCase {
  id: string;
  workflow_template_id: string;
  subject: string;
  started_by_user_id: string | null;
  status: CaseStatus;
  started_at: string;
  completed_at: string | null;
  cancel_reason: string | null;
  // What the job is worth in naira (for example the client's fee); decimals arrive as strings.
  client_value: string | null;
  // The date the client expects the job done. Missing it makes the figure count as lost.
  client_deadline_at: string | null;
  // The state of the figure: none, on_track, at_risk, lost or secured. At risk and lost carry
  // the amount; a case's figure sits in at most one of them.
  value_status: ValueStatus;
  value_at_risk: string;
  value_lost: string;
  created_at: string;
  updated_at: string;
}

export type ValueStatus = "none" | "on_track" | "at_risk" | "lost" | "secured";

export function valueStatusLabel(status: ValueStatus): string {
  if (status === "at_risk") return "At risk";
  if (status === "lost") return "Lost";
  if (status === "secured") return "Secured";
  if (status === "on_track") return "On track";
  return "";
}

export function valueStatusClasses(status: ValueStatus): string {
  if (status === "at_risk") return "bg-amber-500/15 text-amber-300";
  if (status === "lost") return "bg-red-500/15 text-red-300";
  if (status === "secured") return "bg-emerald-500/15 text-emerald-300";
  return "bg-indigo-500/15 text-indigo-300";
}

export interface OverdueTaskBrief {
  id: string;
  title: string;
  assigned_to_employee_id: string | null;
  department_id: string;
  due_at: string | null;
}

export interface ValueCase {
  id: string;
  subject: string;
  status: CaseStatus;
  value_status: ValueStatus;
  client_value: string;
  client_deadline_at: string | null;
  // The tasks holding the figure at risk (empty when it is already lost).
  overdue_tasks: OverdueTaskBrief[];
}

// The money view across the cases the caller may see. Each case's figure is counted ONCE
// in the totals, however many of its tasks are late.
export interface ValueSummary {
  at_risk_total: string;
  lost_total: string;
  secured_total: string;
  on_track_total: string;
  cases_at_risk: number;
  cases_lost: number;
  cases_without_deadline: number;
  cases: ValueCase[];
}

export function loadValueSummary(): Promise<ValueSummary> {
  return apiFetch<ValueSummary>("/workflow-instances/value-summary", { method: "GET" });
}

export interface CaseTask {
  id: string;
  workflow_step_id: string | null;
  // "lead" or "participant" for a step done together by several departments; null for an ordinary step.
  workflow_task_role: "lead" | "participant" | null;
  department_id: string;
  // null = unassigned
  assigned_to_employee_id: string | null;
  title: string;
  status: TaskStatus;
  due_at: string | null;
  completed_at: string | null;
  cancel_reason: string | null;
  created_at: string;
}

export interface CaseDetail extends WorkflowCase {
  // The template's steps AS THEY ARE NOW, in order.
  steps: WorkflowStep[];
  // The tasks this case has created so far, oldest first.
  tasks: CaseTask[];
}

// HR administrators and anyone with the manager role may build templates.
export function canManageTemplates(ctx: CallerContext): boolean {
  return isHr(ctx) || ctx.role === "manager";
}

// Any active employee, and any HR administrator, may start a case.
export function canStartCase(ctx: CallerContext): boolean {
  return isHr(ctx) || ctx.employee !== null;
}

export function canCancelCase(ctx: CallerContext, c: WorkflowCase): boolean {
  if (c.status !== "in_progress") return false;
  return isHr(ctx) || (c.started_by_user_id !== null && c.started_by_user_id === ctx.userId);
}

export function caseStatusLabel(status: string): string {
  if (status === "in_progress") return "In progress";
  if (status === "completed") return "Completed";
  if (status === "cancelled") return "Cancelled";
  return status;
}

export function caseStatusClasses(status: string): string {
  if (status === "completed") return "bg-emerald-500/15 text-emerald-400";
  if (status === "cancelled") return "bg-gray-500/20 text-gray-400";
  return "bg-indigo-500/15 text-indigo-300";
}

export type StepState = "done" | "skipped" | "current" | "waiting";

// The latest task a case made for a step (a step with no task is not reached yet).
export function taskForStep(step: WorkflowStep, tasks: CaseTask[]): CaseTask | null {
  let found: CaseTask | null = null;
  for (const t of tasks) {
    if (t.workflow_step_id === step.id) found = t;
  }
  return found;
}

// Every task a case made for a step, oldest first (a step done together has one per department).
export function tasksForStep(step: WorkflowStep, tasks: CaseTask[]): CaseTask[] {
  return tasks.filter(function (t) {
    return t.workflow_step_id === step.id;
  });
}

// Where a step stands, looking at all of its tasks. With the rule "lead" only the lead's task counts;
// otherwise the step is current while any task is open, done when at least one was completed, and
// skipped when every task was cancelled.
export function stepStateOf(step: WorkflowStep, tasks: CaseTask[]): StepState {
  const mine = tasksForStep(step, tasks);
  if (mine.length === 0) return "waiting";
  if (step.completion_rule === "lead") {
    for (const t of mine) {
      if (t.workflow_task_role === "lead") return stepState(t);
    }
  }
  let anyOpen = false;
  let anyDone = false;
  for (const t of mine) {
    if (t.status === "completed") anyDone = true;
    else if (t.status !== "cancelled") anyOpen = true;
  }
  if (anyOpen) return "current";
  return anyDone ? "done" : "skipped";
}

export function stepState(task: CaseTask | null): StepState {
  if (!task) return "waiting";
  if (task.status === "completed") return "done";
  if (task.status === "cancelled") return "skipped";
  return "current";
}

export function stepStateLabel(state: StepState): string {
  if (state === "done") return "Done";
  if (state === "skipped") return "Skipped";
  if (state === "current") return "Current";
  return "Waiting";
}

export function stepStateClasses(state: StepState): string {
  if (state === "done") return "bg-emerald-500/15 text-emerald-400";
  if (state === "skipped") return "bg-gray-500/20 text-gray-400";
  if (state === "current") return "bg-indigo-500/20 text-indigo-300";
  return "bg-white/5 text-gray-500";
}

// How a task relates to a step done together, for a small label on the case page and the task page.
export function taskRoleLabel(role: "lead" | "participant" | null, rule: CompletionRule): string {
  if (role === "lead") return rule === "lead" ? "Lead" : "Together";
  if (role === "participant") return rule === "lead" ? "Helping" : "Together";
  return "";
}

// Who gets a step's task when no person is named on the step: the department's head, else HR.
// `short` is for a line in the step list; the long form explains it under the "Default person" field.
export function whoReceivesTask(ctx: CallerContext, departmentId: string, short: boolean): string {
  let departmentName = "this department";
  let head: { first_name: string; last_name: string } | null = null;
  for (const d of ctx.departments) {
    if (d.id !== departmentId) continue;
    departmentName = d.name;
    if (d.head_employee_id) {
      for (const e of ctx.employees) {
        if (e.id === d.head_employee_id && e.status !== "inactive") head = e;
      }
    }
  }
  if (head) {
    const headName = head.first_name + " " + head.last_name;
    return short
      ? "Goes to " + headName + " (head)"
      : "If you leave this empty, each task goes to " + headName + ", the head of " + departmentName + ", who then hands it to someone.";
  }
  return short
    ? "Goes to HR (no head)"
    : "If you leave this empty, each task goes to the HR administrators, because " + departmentName + " has no head yet. Name a head in Organization Structure so its own head hands tasks out.";
}

export function turnaroundLabel(hours: number | null, days?: number | null): string {
  if (days !== null && days !== undefined) {
    return days + (days === 1 ? " business day" : " business days");
  }
  if (hours === null || hours === undefined) return "No deadline";
  return hours + (hours === 1 ? " business hour" : " business hours");
}
