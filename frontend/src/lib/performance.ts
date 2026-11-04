import type { CallerContext, Department } from "@/lib/tasks";

// Shapes of the performance endpoints (docs/05_API_DESIGN.md, "Performance (M12)").
// Scores arrive as strings like "66.67" (the server sends exact decimals).
// A score of null means NO DATA, never zero.

export interface KpiScoreLine {
  kpi_id: string;
  kpi_name: string;
  weight: string;
  score_percentage: string | null;
  tasks_on_time: number;
  tasks_late: number;
  tasks_not_done: number;
}

export interface PersonPerformance {
  employee_id: string;
  employee_name: string;
  department_id: string | null;
  period_start: string;
  period_end: string;
  is_final: boolean;
  overall_score: string | null;
  kpis_counted: number;
  kpis_expected: number;
  no_data_reason: string | null;
  kpis: KpiScoreLine[];
}

export interface PersonScoreLine {
  employee_id: string;
  employee_name: string;
  overall_score: string | null;
  kpis_counted: number;
  kpis_expected: number;
}

export interface PageInfo {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface DepartmentPerformance {
  department_id: string;
  department_name: string;
  period_start: string;
  period_end: string;
  is_final: boolean;
  kpi_results_score: string | null;
  kpis_counted: number;
  kpis_expected: number;
  kpi_results_no_data_reason: string | null;
  punctuality_score: string | null;
  punctuality_on_time: number;
  punctuality_late: number;
  punctuality_not_done: number;
  punctuality_no_data_reason: string | null;
  people: PersonScoreLine[];
  people_pagination: PageInfo;
}

export interface LeaderboardEntry {
  rank: number;
  employee_id: string;
  employee_name: string;
  department_id: string;
  department_name: string;
  overall_score: string;
  valid_tasks: number;
  kpis_counted: number;
  kpis_expected: number;
}

export interface Leaderboard {
  period_start: string;
  period_end: string;
  is_final: boolean;
  entries: LeaderboardEntry[];
  pagination: PageInfo;
}

export interface CompanyDepartmentLine {
  department_id: string;
  department_name: string;
  revenue_share: string | null;
  kpi_results_score: string | null;
  kpis_counted: number;
  kpis_expected: number;
  punctuality_score: string | null;
  counted_in_headline: boolean;
}

export interface CompanyTrendPoint {
  period_start: string;
  period_end: string;
  is_final: boolean;
  headline_score: string | null;
  departments_counted: number;
  punctuality_score: string | null;
}

export interface CompanyPerformance {
  period_start: string;
  period_end: string;
  is_final: boolean;
  headline_score: string | null;
  departments_counted: number;
  departments_expected: number;
  headline_is_plain_average: boolean;
  headline_no_data_reason: string | null;
  punctuality_score: string | null;
  punctuality_on_time: number;
  punctuality_late: number;
  punctuality_not_done: number;
  punctuality_no_data_reason: string | null;
  departments: CompanyDepartmentLine[];
  trend: CompanyTrendPoint[];
}

export interface MostImprovedEntry {
  id: string;
  name: string;
  previous_score: string;
  current_score: string;
  change_in_points: string;
  previous_tasks: number;
  current_tasks: number;
}

export interface MostImproved {
  period_start: string;
  period_end: string;
  previous_period_start: string;
  previous_period_end: string;
  min_valid_tasks: number;
  people: MostImprovedEntry[];
  departments: MostImprovedEntry[];
}

// ---- the period being looked at

// start and end are null for "the current quarter": the server then picks the
// company's own current fiscal quarter. Once a response has come back, its
// period_start / period_end are the real dates and the arrows below work from them.
export interface Period {
  start: string | null;
  end: string | null;
}

export const CURRENT_QUARTER: Period = { start: null, end: null };

function toIso(year: number, monthIndex: number, day: number): string {
  const d = new Date(Date.UTC(year, monthIndex, day));
  return d.toISOString().slice(0, 10);
}

function parts(iso: string): { year: number; monthIndex: number; day: number } {
  const bits = iso.split("-");
  return { year: Number(bits[0]), monthIndex: Number(bits[1]) - 1, day: Number(bits[2]) };
}

// The quarter before the one that starts on `startIso` (quarters start on the 1st of a month).
export function previousQuarter(startIso: string): Period {
  const p = parts(startIso);
  return { start: toIso(p.year, p.monthIndex - 3, 1), end: toIso(p.year, p.monthIndex, 0) };
}

// The quarter after the one that ends on `endIso`.
export function nextQuarter(endIso: string): Period {
  const p = parts(endIso);
  // The day after the end is the 1st of the next quarter's first month.
  const start = new Date(Date.UTC(p.year, p.monthIndex, p.day + 1));
  const startYear = start.getUTCFullYear();
  const startMonth = start.getUTCMonth();
  return { start: toIso(startYear, startMonth, 1), end: toIso(startYear, startMonth + 3, 0) };
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

// A quarter that has not started yet has nothing to show, so "next" stops there.
export function startsInFuture(period: Period): boolean {
  return period.start !== null && period.start > todayIso();
}

export function periodLabel(startIso: string, endIso: string): string {
  return formatDay(startIso) + " to " + formatDay(endIso);
}

function formatDay(iso: string): string {
  const p = parts(iso);
  return new Date(Date.UTC(p.year, p.monthIndex, p.day)).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

// ---- URLs

function query(period: Period, extra: string[]): string {
  const items: string[] = [];
  if (period.start !== null && period.end !== null) {
    items.push("period_start=" + period.start);
    items.push("period_end=" + period.end);
  }
  for (const item of extra) {
    items.push(item);
  }
  return items.length === 0 ? "" : "?" + items.join("&");
}

// employeeId "me" is the logged-in person's own card.
export function personPath(employeeId: string, period: Period): string {
  const base = employeeId === "me" ? "/employees/me/performance" : "/employees/" + employeeId + "/performance";
  return base + query(period, []);
}

export function companyPath(period: Period): string {
  return "/company-performance-summary" + query(period, []);
}

export function mostImprovedPath(period: Period): string {
  return "/company-performance-summary/most-improved" + query(period, []);
}

export function departmentPath(departmentId: string, period: Period, page: number): string {
  return "/departments/" + departmentId + "/performance-summary" + query(period, ["page=" + page, "limit=20"]);
}

export function leaderboardPath(departmentId: string, period: Period, page: number): string {
  const extra = ["page=" + page, "limit=20"];
  if (departmentId !== "") {
    extra.push("department_id=" + departmentId);
  }
  return "/employees/leaderboard" + query(period, extra);
}

// ---- showing numbers

// "66.67" -> "66.7", "79.00" -> "79", null -> "No data yet".
export function scoreText(score: string | null): string {
  if (score === null) return "No data yet";
  const rounded = Math.round(Number(score) * 10) / 10;
  return String(rounded);
}

export function scoreClasses(score: string | null): string {
  if (score === null) return "text-gray-500";
  const n = Number(score);
  if (n >= 80) return "text-emerald-300";
  if (n >= 50) return "text-amber-300";
  return "text-red-300";
}

// ---- who gets which screen (the server still decides; this only keeps the menu honest)

export function departmentsICanOpen(ctx: CallerContext): Department[] {
  if (ctx.role === "hr_administrator" || ctx.role === "business_executive") {
    return ctx.departments;
  }
  const mine: Department[] = [];
  for (const d of ctx.departments) {
    const iHeadIt = ctx.employee !== null && d.head_employee_id === ctx.employee.id;
    const iAmManagerThere = ctx.role === "manager" && d.id === ctx.employeeDepartmentId;
    if (iHeadIt || iAmManagerThere) {
      mine.push(d);
    }
  }
  return mine;
}

// The company view is for HR and executives only.
export function canSeeCompany(ctx: CallerContext): boolean {
  return ctx.role === "hr_administrator" || ctx.role === "business_executive";
}

export function canSeeRankedList(ctx: CallerContext): boolean {
  return departmentsICanOpen(ctx).length > 0;
}
