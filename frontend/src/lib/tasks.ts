import { apiFetch, ApiError } from "@/lib/api";

export type TaskStatus = "open" | "in_progress" | "completed" | "cancelled";

export interface Task {
  id: string;
  department_id: string;
  kpi_id: string | null;
  // null = unassigned
  assigned_to_employee_id: string | null;
  title: string;
  description: string | null;
  due_at: string | null;
  completed_at: string | null;
  cancel_reason: string | null;
  status: TaskStatus;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  name: string;
  head_employee_id?: string | null;
}

export interface Employee {
  id: string;
  user_id: string | null;
  first_name: string;
  last_name: string;
  status: string;
  position_id: string;
}

export interface Position {
  id: string;
  department_id: string;
  title: string;
}

export interface Kpi {
  id: string;
  department_id: string;
  name: string;
}

export interface PaginationInfo {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationInfo;
}

export async function fetchAllPages<T>(path: string): Promise<T[]> {
  const all: T[] = [];
  const joiner = path.indexOf("?") === -1 ? "?" : "&";
  let page = 1;
  while (page <= 50) {
    const res = await apiFetch<PaginatedResponse<T>>(path + joiner + "page=" + page + "&limit=100", {
      method: "GET",
    });
    for (const item of res.data) {
      all.push(item);
    }
    if (!res.pagination.has_next) break;
    page = page + 1;
  }
  return all;
}

interface MeResponse {
  user: { id: string; full_name: string };
  memberships: { role: string; deactivated_at: string | null }[];
}

// Everything the task screens need to know about the person looking at them,
// so each screen can hide the actions they can't use. The server still
// decides what is actually allowed; this only keeps the buttons honest.
export interface CallerContext {
  userId: string;
  userName: string;
  role: string;
  employee: Employee | null;
  // The department the caller's own position belongs to, if any.
  employeeDepartmentId: string | null;
  departments: Department[];
  employees: Employee[];
  kpis: Kpi[];
}

export async function loadCaller(): Promise<CallerContext> {
  const results = await Promise.all([
    apiFetch<MeResponse>("/auth/me", { method: "GET" }),
    fetchAllPages<Department>("/departments"),
    fetchAllPages<Employee>("/employees"),
    fetchAllPages<Position>("/positions"),
  ]);
  const me = results[0];
  const departments = results[1];
  const employees = results[2];
  const positions = results[3];

  // A person can belong to several organizations; the first active
  // membership is used for the role until an organization switcher exists.
  let role = "";
  for (const m of me.memberships) {
    if (!m.deactivated_at) {
      role = m.role;
      break;
    }
  }

  let employee: Employee | null = null;
  for (const e of employees) {
    if (e.user_id === me.user.id && e.status !== "inactive") {
      employee = e;
      break;
    }
  }

  let employeeDepartmentId: string | null = null;
  if (employee) {
    for (const p of positions) {
      if (p.id === employee.position_id) {
        employeeDepartmentId = p.department_id;
        break;
      }
    }
  }

  // KPI names for the task forms; a department whose KPIs fail to load is
  // simply left out rather than blocking the screen.
  const kpiLists = await Promise.all(
    departments.map(function (d) {
      return fetchAllPages<Kpi>("/kpis?department_id=" + d.id).catch(function () {
        return [] as Kpi[];
      });
    })
  );
  const kpis: Kpi[] = [];
  for (const list of kpiLists) {
    for (const k of list) {
      kpis.push(k);
    }
  }

  return {
    userId: me.user.id,
    userName: me.user.full_name,
    role: role,
    employee: employee,
    employeeDepartmentId: employeeDepartmentId,
    departments: departments,
    employees: employees,
    kpis: kpis,
  };
}

export function roleLabel(role: string): string {
  if (role === "hr_administrator") return "HR Administrator";
  if (role === "business_executive") return "Business Executive";
  if (role === "manager") return "Manager";
  if (role === "system_administrator") return "System Administrator";
  if (role === "employee") return "Employee";
  return role;
}

export function fullName(e: Employee): string {
  return (e.first_name + " " + e.last_name).trim();
}

export function employeeName(ctx: CallerContext, id: string | null): string {
  if (!id) return "Unassigned";
  for (const e of ctx.employees) {
    if (e.id === id) return fullName(e);
  }
  return "Unknown employee";
}

export function departmentName(ctx: CallerContext, id: string | null): string {
  for (const d of ctx.departments) {
    if (d.id === id) return d.name;
  }
  return "Unknown department";
}

export function activeEmployees(ctx: CallerContext): Employee[] {
  return ctx.employees.filter(function (e) {
    return e.status !== "inactive";
  });
}

// ---- who may do what (mirrors the server rules; the server has the last word)

export function isHr(ctx: CallerContext): boolean {
  return ctx.role === "hr_administrator";
}

export function isHeadOf(ctx: CallerContext, departmentId: string): boolean {
  if (!ctx.employee) return false;
  for (const d of ctx.departments) {
    if (d.id === departmentId) {
      return d.head_employee_id === ctx.employee.id;
    }
  }
  return false;
}

export function headsAnyDepartment(ctx: CallerContext): boolean {
  if (!ctx.employee) return false;
  for (const d of ctx.departments) {
    if (d.head_employee_id === ctx.employee.id) return true;
  }
  return false;
}

export function canCreateTasks(ctx: CallerContext): boolean {
  return isHr(ctx) || ctx.role === "manager" || headsAnyDepartment(ctx);
}

// HR and the department's head may choose anyone; so may a creator who works
// in that same department. Anyone else's task goes to the department head.
export function canPickAssignee(ctx: CallerContext, departmentId: string): boolean {
  return isHr(ctx) || isHeadOf(ctx, departmentId) || ctx.employeeDepartmentId === departmentId;
}

function isCreator(ctx: CallerContext, task: Task): boolean {
  return task.created_by_user_id !== null && task.created_by_user_id === ctx.userId;
}

function isAssignee(ctx: CallerContext, task: Task): boolean {
  return ctx.employee !== null && task.assigned_to_employee_id === ctx.employee.id;
}

export function canEditTask(ctx: CallerContext, task: Task): boolean {
  return isHr(ctx) || isHeadOf(ctx, task.department_id) || isCreator(ctx, task);
}

export function canCompleteTask(ctx: CallerContext, task: Task): boolean {
  return isHr(ctx) || isHeadOf(ctx, task.department_id) || isAssignee(ctx, task);
}

export function canCancelTask(ctx: CallerContext, task: Task): boolean {
  return isHr(ctx) || isHeadOf(ctx, task.department_id) || isCreator(ctx, task);
}

export function canReassignTask(ctx: CallerContext, task: Task): boolean {
  return (
    isHr(ctx) ||
    isHeadOf(ctx, task.department_id) ||
    (isCreator(ctx, task) && ctx.employeeDepartmentId === task.department_id)
  );
}

// ---- small shared helpers

export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  return fallback;
}

export function isNotClockedIn(err: unknown): boolean {
  return err instanceof ApiError && err.code === "NOT_CLOCKED_IN";
}

export function statusLabel(status: string): string {
  if (status === "open") return "Open";
  if (status === "in_progress") return "In progress";
  if (status === "completed") return "Completed";
  if (status === "cancelled") return "Cancelled";
  return status;
}

export function statusClasses(status: string): string {
  if (status === "completed") return "bg-emerald-500/15 text-emerald-400";
  if (status === "cancelled") return "bg-gray-500/20 text-gray-400";
  if (status === "in_progress") return "bg-cyan-500/15 text-cyan-300";
  return "bg-indigo-500/15 text-indigo-300";
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "No deadline";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function isPastDue(task: Task): boolean {
  if (!task.due_at) return false;
  if (task.status !== "open" && task.status !== "in_progress") return false;
  return new Date(task.due_at).getTime() < Date.now();
}

// <input type="datetime-local"> works in the person's local time with no
// offset. The server needs an offset, so the picked time is converted to a
// full ISO instant (which carries one) before sending.
export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  function pad(n: number): string {
    return n < 10 ? "0" + n : String(n);
  }
  return (
    d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes())
  );
}
