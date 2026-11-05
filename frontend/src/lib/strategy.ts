import { fetchAllPages } from "@/lib/tasks";
import { apiFetch } from "@/lib/api";

export interface KeyResult {
  id: string;
  okr_id: string;
  description: string;
  target_date: string | null;
}

export interface Objective {
  id: string;
  title: string;
  // null = a company-wide objective.
  department_id: string | null;
  keyResults: KeyResult[];
}

interface ObjectiveRow {
  id: string;
  title: string;
  department_id: string | null;
}

// One call for the objectives, then one per objective for its key results.
// Fine for the dozens of objectives a company has; the lists are paged
// inside fetchAllPages so nothing is cut off at 100.
export async function loadObjectives(): Promise<Objective[]> {
  const rows = await fetchAllPages<ObjectiveRow>("/okrs");
  const keyResultLists = await Promise.all(
    rows.map(function (row) {
      return fetchAllPages<KeyResult>("/okrs/" + row.id + "/key-results");
    })
  );
  const out: Objective[] = [];
  for (let i = 0; i < rows.length; i++) {
    out.push({
      id: rows[i].id,
      title: rows[i].title,
      department_id: rows[i].department_id,
      keyResults: keyResultLists[i],
    });
  }
  return out;
}

// A KPI that measures a key result, as the Strategy screen describes it.
export interface MeasuringKpi {
  name: string;
  weight: string;
  target_value: string | null;
  unit: string | null;
  is_inverse: boolean;
}

interface KpiRow extends MeasuringKpi {
  key_result_id: string | null;
}

// Key result id -> the KPIs that measure it (only KPIs that are linked to one).
export async function loadMeasuringKpis(): Promise<Record<string, MeasuringKpi[]>> {
  const rows = await fetchAllPages<KpiRow>("/kpis");
  const byKeyResult: Record<string, MeasuringKpi[]> = {};
  for (const row of rows) {
    if (row.key_result_id === null) continue;
    if (!byKeyResult[row.key_result_id]) byKeyResult[row.key_result_id] = [];
    byKeyResult[row.key_result_id].push(row);
  }
  return byKeyResult;
}

export async function addObjective(title: string, departmentId: string | null): Promise<void> {
  await apiFetch("/okrs", { method: "POST", body: { title: title, department_id: departmentId } });
}

export async function renameObjective(id: string, title: string): Promise<void> {
  await apiFetch("/okrs/" + id, { method: "PATCH", body: { title: title } });
}

export async function addKeyResult(okrId: string, description: string, targetDate: string | null): Promise<void> {
  await apiFetch("/okrs/" + okrId + "/key-results", {
    method: "POST",
    body: { description: description, target_date: targetDate },
  });
}

// The server refuses (409) while a KPI still measures a key result, and its
// message says how many; the screen shows that message as it is.
export async function deleteObjective(id: string): Promise<void> {
  await apiFetch("/okrs/" + id, { method: "DELETE" });
}

export async function deleteKeyResult(id: string): Promise<void> {
  await apiFetch("/key-results/" + id, { method: "DELETE" });
}

export async function editKeyResult(id: string, description: string, targetDate: string | null): Promise<void> {
  await apiFetch("/key-results/" + id, {
    method: "PATCH",
    body: { description: description, target_date: targetDate },
  });
}
