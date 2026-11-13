"use client";

import { useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import OrgChartView from "@/components/OrgChartView";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchAllPages, fullName, roleLabel } from "@/lib/tasks";
import type { Employee, Position } from "@/lib/tasks";
import { isHrRole, loadMe } from "@/lib/settings";
import { personLabel } from "@/lib/personLabel";
import { useLoad } from "@/lib/useLoad";

interface DepartmentRow {
  id: string;
  name: string;
  head_employee_id: string | null;
}

interface ChartPosition extends Position {
  reports_to_position_id: string | null;
}

interface MemberRow {
  id: string;
  role: string;
  user: { id: string };
}

interface ChartData {
  canEdit: boolean;
  departments: DepartmentRow[];
  positions: ChartPosition[];
  employees: Employee[];
  // Each login's membership (id and access level), by user id. Only HR can read the team list.
  members: Record<string, MemberRow>;
}

const ACCESS_LEVELS = ["employee", "manager", "business_executive", "hr_administrator"];

async function loadChart(): Promise<ChartData> {
  const me = await loadMe();
  const canEdit = isHrRole(me.role);
  const results = await Promise.all([
    fetchAllPages<DepartmentRow>("/departments"),
    fetchAllPages<ChartPosition>("/positions"),
    fetchAllPages<Employee>("/employees"),
  ]);
  const members: Record<string, MemberRow> = {};
  if (canEdit) {
    try {
      const rows = await fetchAllPages<MemberRow>("/memberships");
      for (const row of rows) members[row.user.id] = row;
    } catch {
      // The chart still works without access levels.
    }
  }
  return { canEdit: canEdit, departments: results[0], positions: results[1], employees: results[2], members: members };
}

export default function EmployeeChartPage() {
  const [reload, setReload] = useState(0);
  const state = useLoad<ChartData>("employee-chart|" + reload, loadChart, "Couldn't load the chart. Check your connection and try again.");
  const [pickedId, setPickedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const data = state.data;
  const person = data ? data.employees.find(function (e) { return e.id === pickedId; }) : undefined;
  const position = person && data ? data.positions.find(function (p) { return p.id === person.position_id; }) : undefined;
  const department = position && data ? data.departments.find(function (d) { return d.id === position.department_id; }) : undefined;
  const member = person && person.user_id && data ? data.members[person.user_id] : undefined;
  const isHead = person && department ? department.head_employee_id === person.id : false;

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(done);
      setReload(reload + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that change.");
    } finally {
      setBusy(false);
    }
  }

  function makeHead() {
    if (!person || !department) return;
    run(function () {
      return apiFetch("/departments/" + department.id, { method: "PATCH", body: { head_employee_id: person.id } });
    }, fullName(person) + " is now the head of " + department.name + ".");
  }

  function setAccessLevel(role: string) {
    if (!member) return;
    run(function () {
      return apiFetch("/memberships/" + member.id, { method: "PATCH", body: { role: role } });
    }, "Access level changed to " + roleLabel(role) + ".");
  }

  return (
    <AppShell activeLabel="Employees" title="Org chart" breadcrumb="Dashboard > Employees > Org chart">
      {state.loading ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {state.error ? <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p> : null}

      {data ? (
        <>
          <p className="text-sm text-gray-400">
            Every role with the people in it. A star marks a department head; &quot;Vacant&quot; means nobody holds that role yet.
            Click a person to see their details{data.canEdit ? " and change their access level or make them head of their department" : ""}.
          </p>

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
            <OrgChartView
              positions={data.positions}
              employees={data.employees}
              departments={data.departments}
              headIds={data.departments.map(function (d) { return d.head_employee_id || ""; }).filter(function (id) { return id !== ""; })}
              selectedPersonId={pickedId}
              onSelectPerson={function (id) { setPickedId(id); setMessage(""); setError(""); }}
            />
          </div>

          {error ? <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
          {message ? <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{message}</p> : null}

          {person ? (
            <div className="rounded-2xl border border-indigo-400/30 bg-[#0a0e1a] p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-base font-semibold text-white">{fullName(person)}</p>
                  <p className="text-xs text-gray-400">{personLabel(person, data.positions, data.departments)}</p>
                  {isHead && department ? <p className="mt-1 text-xs font-semibold text-amber-300">★ Head of {department.name}</p> : null}
                </div>
                <Link href={"/employees/" + person.id} className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-200 hover:bg-white/5">
                  Open profile
                </Link>
              </div>

              {data.canEdit ? (
                <div className="mt-4 flex flex-wrap items-end gap-4">
                  {department && !isHead ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={makeHead}
                      className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50"
                    >
                      Make head of {department.name}
                    </button>
                  ) : null}
                  {member ? (
                    <label className="text-xs text-gray-400">
                      Access level
                      <select
                        value={member.role}
                        disabled={busy}
                        onChange={function (e) { setAccessLevel(e.target.value); }}
                        className="mt-1 block rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500"
                      >
                        {ACCESS_LEVELS.map(function (role) {
                          return <option key={role} value={role}>{roleLabel(role)}</option>;
                        })}
                      </select>
                    </label>
                  ) : (
                    <p className="text-xs text-gray-500">No login yet, so no access level. Give them one from their profile.</p>
                  )}
                </div>
              ) : null}

              {data.canEdit && isHead && member && member.role === "employee" ? (
                <p className="mt-3 text-xs text-indigo-300">
                  A department head usually has the Manager access level, so they can manage their team&apos;s tasks.{" "}
                  <button type="button" disabled={busy} onClick={function () { setAccessLevel("manager"); }} className="font-medium underline">
                    Set to Manager
                  </button>
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </AppShell>
  );
}
