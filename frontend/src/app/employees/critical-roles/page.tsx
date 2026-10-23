"use client";

import Link from "next/link";
import AppShell from "@/components/AppShell";
import { fetchAllPages, fullName, roleLabel } from "@/lib/tasks";
import type { Department, Employee } from "@/lib/tasks";
import { loadMe } from "@/lib/settings";
import type { MeData } from "@/lib/settings";
import { CRITICALITY_OPTIONS, RISK_OPTIONS, isHighRisk, optionLabel, riskClasses } from "@/lib/criticalRoles";
import { useLoad } from "@/lib/useLoad";

interface CriticalPosition {
  id: string;
  department_id: string;
  title: string;
  is_critical: boolean;
  risk_level: string | null;
  criticality_type: string | null;
}

interface Row {
  position: CriticalPosition;
  department: string;
  holders: string[];
}

interface PageData {
  me: MeData;
  rows: Row[];
  pendingSuggestions: number;
}

async function loadPage(): Promise<PageData> {
  const me = await loadMe();
  const results = await Promise.all([
    fetchAllPages<CriticalPosition>("/positions"),
    fetchAllPages<Department>("/departments"),
    fetchAllPages<Employee>("/employees"),
  ]);
  const positions = results[0];
  const departments = results[1];
  const employees = results[2];

  const departmentName: Record<string, string> = {};
  for (const d of departments) departmentName[d.id] = d.name;

  const holdersOf: Record<string, string[]> = {};
  for (const e of employees) {
    if (e.status !== "active") continue;
    if (!holdersOf[e.position_id]) holdersOf[e.position_id] = [];
    holdersOf[e.position_id].push(fullName(e));
  }

  const rows: Row[] = positions
    .filter(function (p) {
      return p.is_critical;
    })
    .map(function (p) {
      return { position: p, department: departmentName[p.department_id] || "Unknown department", holders: holdersOf[p.id] || [] };
    });

  // The number of AI suggestions waiting for review is a nice-to-have.
  let pendingSuggestions = 0;
  try {
    const pending = await fetchAllPages<{ id: string }>("/ai-suggestions?status=pending&suggestion_type=critical_position");
    pendingSuggestions = pending.length;
  } catch {
    // Not everyone can read suggestions; the registry itself still works.
  }
  return { me: me, rows: rows, pendingSuggestions: pendingSuggestions };
}

const STAT = "rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl";

export default function CriticalRolesPage() {
  const state = useLoad<PageData>("critical-roles", loadPage, "Couldn't load critical roles. Check your connection and try again.");
  const data = state.data;
  const rows = data ? data.rows : [];
  const vacant = rows.filter(function (r) {
    return r.holders.length === 0;
  }).length;
  const highRisk = rows.filter(function (r) {
    return isHighRisk(r.position.risk_level);
  }).length;

  return (
    <AppShell
      activeLabel="Employees"
      title="Critical Roles"
      breadcrumb="Employees > Critical Roles"
      userName={data ? data.me.fullName : undefined}
      userRole={data ? roleLabel(data.me.role) : undefined}
    >
      {state.error ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className={STAT}>
          <p className="text-xs uppercase tracking-wide text-gray-500">Critical roles</p>
          <p className="mt-2 text-2xl font-bold text-white">{data ? rows.length : "–"}</p>
          <p className="mt-1 text-xs text-gray-500">Across all departments</p>
        </div>
        <div className={STAT}>
          <p className="text-xs uppercase tracking-wide text-gray-500">Filled</p>
          <p className="mt-2 text-2xl font-bold text-emerald-400">{data ? rows.length - vacant : "–"}</p>
          <p className="mt-1 text-xs text-gray-500">Have an active employee</p>
        </div>
        <div className={STAT}>
          <p className="text-xs uppercase tracking-wide text-gray-500">Vacant</p>
          <p className="mt-2 text-2xl font-bold text-red-400">{data ? vacant : "–"}</p>
          <p className="mt-1 text-xs text-gray-500">No active employee in the role</p>
        </div>
        <div className={STAT}>
          <p className="text-xs uppercase tracking-wide text-gray-500">High risk</p>
          <p className="mt-2 text-2xl font-bold text-amber-400">{data ? highRisk : "–"}</p>
          <p className="mt-1 text-xs text-gray-500">Rated high or very high</p>
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-white">Critical Roles Registry</h3>
          <Link href="/employees/critical-roles/ai-suggestions" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
            {data && data.pendingSuggestions > 0
              ? "Review " + data.pendingSuggestions + (data.pendingSuggestions === 1 ? " new suggestion" : " new suggestions") + " →"
              : "Review AI suggestions →"}
          </Link>
        </div>

        {state.loading ? (
          <p className="mt-4 text-sm text-gray-500">Loading…</p>
        ) : rows.length === 0 && !state.error ? (
          <p className="mt-4 text-sm text-gray-500">
            No roles are marked critical yet. They appear here once you approve a critical-role suggestion from the AI.
          </p>
        ) : rows.length > 0 ? (
          <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-4 py-3 font-medium">Role</th>
                  <th className="px-4 py-3 font-medium">Department</th>
                  <th className="px-4 py-3 font-medium">Current holder</th>
                  <th className="px-4 py-3 font-medium">Why it is critical</th>
                  <th className="px-4 py-3 font-medium">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {rows.map(function (r) {
                  return (
                    <tr key={r.position.id} className="transition hover:bg-white/5">
                      <td className="px-4 py-4 font-medium text-white">{r.position.title}</td>
                      <td className="px-4 py-4 text-gray-300">{r.department}</td>
                      <td className="px-4 py-4 text-gray-300">
                        {r.holders.length > 0 ? r.holders.join(", ") : <span className="text-red-400">Vacant</span>}
                      </td>
                      <td className="px-4 py-4">
                        <span className="rounded-full bg-indigo-500/15 px-2.5 py-1 text-xs font-medium text-indigo-300">
                          {optionLabel(CRITICALITY_OPTIONS, r.position.criticality_type)}
                        </span>
                      </td>
                      <td className="px-4 py-4">
                        <span className={"rounded-full px-2.5 py-1 text-xs font-medium " + riskClasses(r.position.risk_level)}>
                          {optionLabel(RISK_OPTIONS, r.position.risk_level)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
