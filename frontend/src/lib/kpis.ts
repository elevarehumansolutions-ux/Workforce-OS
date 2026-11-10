import { apiFetch } from "@/lib/api";
import { fetchAllPages } from "@/lib/tasks";
import { CURRENT_QUARTER, departmentPath } from "@/lib/performance";

// Decimals (weight, target) arrive from the API as strings, e.g. "40.00".
export interface KpiFull {
  id: string;
  department_id: string;
  // KPIs for one location form their own weight group (null = department-wide).
  location_id: string | null;
  key_result_id: string | null;
  name: string;
  description: string | null;
  weight: string;
  is_inverse: boolean;
  target_value: string | null;
  unit: string | null;
  tracking_mode: "manual" | "task_count";
}

export interface KpiScoreRow {
  period_start: string;
  period_end: string;
  actual_value: string | null;
  score_percentage: string | null;
}

export interface TaskProgress {
  completed_tasks: number;
  target_value: string | null;
  unit: string | null;
  score_percentage: string | null;
}

export interface KpiForm {
  name: string;
  // What the KPI measures, in plain words (optional).
  description: string;
  // The key result this KPI measures ("" = none). It ties the KPI to the strategy: the objective
  // and key result show which KPIs measure them. (Employees are scored from tasks linked to the
  // KPI, not from this link.)
  keyResultId: string;
  weight: string;
  target: string;
  unit: string;
  isInverse: boolean;
  trackingMode: "manual" | "task_count";
}

// What a department is expected to return in a year: its share of the capital
// investment (set on the department) x the capital amount (Business DNA, which only
// HR and executives may read). Either part missing means "not known": share and
// amount are null and the screen says so instead of showing zero.
export interface DepartmentReturn {
  sharePct: number | null;
  capital: number | null;
  // The department's revenue target for a year (share x capital).
  annualReturn: number | null;
  // Estimated profit margin in percent, and revenue target x margin.
  marginPct: number | null;
  annualProfit: number | null;
}

export async function loadDepartmentReturn(departmentId: string): Promise<DepartmentReturn> {
  const department = await apiFetch<{
    revenue_allocation_percentage: string | number | null;
    profit_margin_percentage: string | number | null;
  }>(
    "/departments/" + departmentId,
    { method: "GET" }
  );
  let capital: number | null = null;
  try {
    const dna = await apiFetch<{ capital_investment_amount: string | number | null }>("/business-dna", { method: "GET" });
    const amount = Number(dna.capital_investment_amount);
    capital = dna.capital_investment_amount !== null && amount > 0 ? amount : null;
  } catch {
    // Someone who may not read the capital amount still sees the percentage.
  }
  const raw = department.revenue_allocation_percentage;
  const sharePct = raw === null || raw === undefined ? null : Number(raw);
  const annual = capital !== null && sharePct !== null ? (capital * sharePct) / 100 : null;
  const marginRaw = department.profit_margin_percentage;
  const marginPct = marginRaw === null || marginRaw === undefined ? null : Number(marginRaw);
  const profit = annual !== null && marginPct !== null ? (annual * marginPct) / 100 : null;
  return { sharePct: sharePct, capital: capital, annualReturn: annual, marginPct: marginPct, annualProfit: profit };
}

export function loadKpisOfDepartment(departmentId: string): Promise<KpiFull[]> {
  return fetchAllPages<KpiFull>("/kpis?department_id=" + departmentId);
}

// What the weights of a department add up to, so the screen can say
// "85 of 100 used" and HR sees how much room is left.
export function weightTotal(kpis: KpiFull[]): number {
  let total = 0;
  for (const k of kpis) {
    total = total + Number(k.weight);
  }
  return total;
}

function bodyFromForm(form: KpiForm) {
  return {
    name: form.name.trim(),
    description: form.description.trim() === "" ? null : form.description.trim(),
    key_result_id: form.keyResultId === "" ? null : form.keyResultId,
    weight: form.weight,
    target_value: form.target.trim() === "" ? null : form.target.trim(),
    unit: form.unit.trim() === "" ? null : form.unit.trim(),
    is_inverse: form.isInverse,
    tracking_mode: form.trackingMode,
  };
}

export async function createKpi(departmentId: string, form: KpiForm): Promise<void> {
  const body = { ...bodyFromForm(form), department_id: departmentId };
  await apiFetch("/kpis", { method: "POST", body: body });
}

// Change only the weight of one KPI. PATCH leaves every field that is not sent alone, and the
// server still refuses a weight that would push the department over 100%.
export async function updateKpiWeight(kpiId: string, weight: string): Promise<void> {
  await apiFetch("/kpis/" + kpiId, { method: "PATCH", body: { weight: weight } });
}

export async function updateKpi(kpiId: string, form: KpiForm): Promise<void> {
  await apiFetch("/kpis/" + kpiId, { method: "PATCH", body: bodyFromForm(form) });
}

// The only way to delete a KPI is to send the department's WHOLE list again
// without it, and the weights of what is left must not total more than 100
// (short of 100, or nothing left, is accepted). So the caller passes the KPIs
// that stay plus the weight each should now have.
// Every field is sent again because this call replaces the KPI's values.
export async function deleteKpi(
  departmentId: string,
  locationId: string | null,
  staying: KpiFull[],
  newWeights: Record<string, string>
): Promise<void> {
  const items = staying.map(function (k) {
    return {
      id: k.id,
      name: k.name,
      description: k.description,
      weight: newWeights[k.id],
      is_inverse: k.is_inverse,
      target_value: k.target_value,
      unit: k.unit,
      key_result_id: k.key_result_id,
    };
  });
  const query = locationId ? "?location_id=" + locationId : "";
  await apiFetch("/departments/" + departmentId + "/kpis" + query, { method: "PUT", body: { kpis: items } });
}

export async function loadLatestScore(kpiId: string): Promise<KpiScoreRow | null> {
  const res = await apiFetch<{ data: KpiScoreRow[] }>("/kpis/" + kpiId + "/scores?limit=1", { method: "GET" });
  return res.data.length > 0 ? res.data[0] : null;
}

export function loadTaskProgress(kpiId: string): Promise<TaskProgress> {
  return apiFetch<TaskProgress>("/kpis/" + kpiId + "/task-progress", { method: "GET" });
}

// The server decides which quarter is "now" (it knows the fiscal year), so we
// read its dates from the department performance answer instead of guessing.
export async function currentPeriodDates(departmentId: string): Promise<{ start: string; end: string }> {
  const res = await apiFetch<{ period_start: string; period_end: string }>(
    departmentPath(departmentId, CURRENT_QUARTER, 1),
    { method: "GET" }
  );
  return { start: res.period_start, end: res.period_end };
}

export async function recordResult(kpiId: string, departmentId: string, actualValue: string): Promise<void> {
  const period = await currentPeriodDates(departmentId);
  await apiFetch("/kpis/" + kpiId + "/scores", {
    method: "POST",
    body: { period_start: period.start, period_end: period.end, actual_value: actualValue },
  });
}
