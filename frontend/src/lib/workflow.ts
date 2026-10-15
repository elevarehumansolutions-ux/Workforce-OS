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
  // null = the task lands with the department
  default_assignee_employee_id: string | null;
  // null = no deadline. Counted in business hours (Mon-Fri 09:00-17:00).
  default_turnaround_hours: number | null;
  created_at: string;
  updated_at: string;
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
  created_at: string;
  updated_at: string;
}

export interface CaseTask {
  id: string;
  workflow_step_id: string | null;
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

export function turnaroundLabel(hours: number | null): string {
  if (hours === null || hours === undefined) return "No deadline";
  return hours + (hours === 1 ? " business hour" : " business hours");
}
