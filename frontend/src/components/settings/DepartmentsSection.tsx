"use client";

import { useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchAllPages, fullName } from "@/lib/tasks";
import type { Employee } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { SETTINGS_INPUT_CLASS, isHrRole } from "@/lib/settings";
import type { SectionProps } from "./types";

interface DepartmentRow {
  id: string;
  name: string;
  is_critical: boolean;
  revenue_allocation_percentage: string | number | null;
  head_employee_id: string | null;
}

interface DepartmentData {
  departments: DepartmentRow[];
  employees: Employee[];
}

export default function DepartmentsSection(props: SectionProps) {
  const canEdit = isHrRole(props.me.role);
  const [reloadCounter, setReloadCounter] = useState(0);
  const state = useLoad<DepartmentData>(
    "departments|" + reloadCounter,
    async function () {
      const results = await Promise.all([fetchAllPages<DepartmentRow>("/departments"), fetchAllPages<Employee>("/employees")]);
      return { departments: results[0], employees: results[1] };
    },
    "Couldn't load the departments."
  );
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  const departments = state.data ? state.data.departments : [];
  const employees = state.data ? state.data.employees : [];
  const pickable = employees.filter(function (e) {
    return e.status !== "inactive";
  });

  function headName(id: string | null): string {
    if (!id) return "No head set";
    for (const e of employees) {
      if (e.id === id) return fullName(e);
    }
    return "Unknown employee";
  }

  async function changeHead(department: DepartmentRow, employeeId: string) {
    setError("");
    setBusyId(department.id);
    try {
      await apiFetch("/departments/" + department.id, {
        method: "PATCH",
        body: { head_employee_id: employeeId === "" ? null : employeeId },
      });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change the head. Check your connection and try again.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-white">Departments</h3>
          <p className="mt-1 text-sm text-gray-500">Who leads each department and how much of revenue it carries.</p>
        </div>
        <Link href="/organization-structure" className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/5">
          Open organization structure
        </Link>
      </div>

      {error ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
      {state.loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}
      {state.error ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p> : null}

      {!state.loading && !state.error ? (
        departments.length === 0 ? (
          <p className="mt-6 text-sm text-gray-500">No departments yet. Add them in the organization structure.</p>
        ) : (
          <div className="mt-6 overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-white/5 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Department</th>
                  <th className="px-4 py-3 font-medium">Critical</th>
                  <th className="px-4 py-3 font-medium">Revenue share</th>
                  <th className="px-4 py-3 font-medium">Head</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {departments.map(function (d) {
                  return (
                    <tr key={d.id}>
                      <td className="px-4 py-3 font-medium text-white">{d.name}</td>
                      <td className="px-4 py-3">
                        {d.is_critical ? (
                          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-300">Critical</span>
                        ) : (
                          <span className="text-gray-500">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-300">
                        {d.revenue_allocation_percentage !== null && d.revenue_allocation_percentage !== undefined ? Number(d.revenue_allocation_percentage) + "%" : "Not set"}
                      </td>
                      <td className="px-4 py-3">
                        {canEdit ? (
                          <select
                            value={d.head_employee_id || ""}
                            disabled={busyId === d.id}
                            onChange={function (e) {
                              changeHead(d, e.target.value);
                            }}
                            className={SETTINGS_INPUT_CLASS}
                          >
                            <option value="">No head set</option>
                            {pickable.map(function (e) {
                              return (
                                <option key={e.id} value={e.id}>
                                  {fullName(e)}
                                </option>
                              );
                            })}
                          </select>
                        ) : (
                          <span className="text-gray-300">{headName(d.head_employee_id)}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      ) : null}
      <p className="mt-4 text-xs text-gray-500">
        Department heads can create and manage tasks in their own department.{canEdit ? "" : " Only an HR administrator can change who leads one."}
      </p>
    </div>
  );
}
