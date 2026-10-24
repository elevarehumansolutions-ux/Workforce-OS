"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";
import { resumePath } from "@/lib/onboarding";
import AppShell from "@/components/AppShell";
import { fetchAllPages, fullName, roleLabel, formatDateTime } from "@/lib/tasks";
import type { Department, Employee, PaginatedResponse, Position } from "@/lib/tasks";
import { canReadAuditLog, isHrRole, loadMe, titleCase } from "@/lib/settings";
import type { MeData } from "@/lib/settings";
import { useLoad } from "@/lib/useLoad";

interface MeResponse {
  user: { id: string; account_status: string };
}

export default function DashboardPage() {
  const router = useRouter();
  // Starts true on both the server and client's first render (see the
  // Business DNA / verify-email fixes for why this can't read anything
  // client-only here) and only flips once the checks below clear, so the
  // dashboard never flashes before we know onboarding is actually done.
  const [checking, setChecking] = useState(true);

  useEffect(function () {
    let cancelled = false;
    async function guard() {
      if (!getAccessToken()) {
        router.replace("/login");
        return;
      }
      try {
        const me = await apiFetch<MeResponse>("/auth/me", { method: "GET" });
        if (cancelled) return;
        if (me.user.account_status !== "verified") {
          router.replace("/verify-email");
          return;
        }
        // Unfinished onboarding: back to the step they stopped at.
        const resume = resumePath(me.user.id);
        if (resume) {
          router.replace(resume);
          return;
        }
      } catch {
        // If /me itself fails, don't block the dashboard on it — apiFetch
        // already sends the person to /login on an unrecoverable 401.
        if (!cancelled) setChecking(false);
        return;
      }

      try {
        // There's no dedicated "onboarding_complete" flag on the API yet —
        // GET /business-dna 404ing is the most honest signal available
        // that the wizard was never finished (it's the first step, and
        // PUT /business-dna is what creates the profile). Worth asking
        // Emmanuel for a real flag if this ever gets more steps to check.
        await apiFetch("/business-dna", { method: "GET" });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace("/onboarding/business-dna");
          return;
        }
        // Any other failure (network blip, etc.): fail open rather than
        // trap the person on a loading screen.
      }

      if (!cancelled) setChecking(false);
    }
    guard();
    return function () {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (checking) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#05070f] text-white">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
      </div>
    );
  }

  return <DashboardBody />;
}

interface AttendanceRow {
  id: string;
  employee_id: string;
  clock_in_at: string;
  clock_out_at: string | null;
}

interface AuditRow {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  created_at: string;
}

interface DeptSummary {
  id: string;
  name: string;
  isCritical: boolean;
  headcount: number;
  head: string;
}

interface DashboardData {
  me: MeData;
  activeCount: number | null;
  departments: DeptSummary[];
  // null = this person can't see it (or it couldn't be loaded).
  attendance: { present: number; clockedInNow: number; names: string[] } | null;
  openTasks: number | null;
  inProgressTasks: number | null;
  vacantCritical: number | null;
  activity: AuditRow[] | null;
  actors: Record<string, string>;
}

interface DepartmentFull extends Department {
  is_critical: boolean;
}

interface PositionFull extends Position {
  is_critical: boolean;
}

function todayLocal(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + m + "-" + day;
}

async function total(path: string): Promise<number | null> {
  try {
    const res = await apiFetch<PaginatedResponse<unknown>>(path, { method: "GET" });
    return res.pagination.total;
  } catch {
    return null;
  }
}

async function loadDashboard(): Promise<DashboardData> {
  const me = await loadMe();
  const seesOrg = canReadAuditLog(me.role) || me.role === "manager";
  const result: DashboardData = {
    me: me,
    activeCount: null,
    departments: [],
    attendance: null,
    openTasks: null,
    inProgressTasks: null,
    vacantCritical: null,
    activity: null,
    actors: {},
  };

  let employees: Employee[] = [];
  let departments: DepartmentFull[] = [];
  let positions: PositionFull[] = [];
  if (seesOrg) {
    try {
      const loaded = await Promise.all([
        fetchAllPages<Employee>("/employees"),
        fetchAllPages<DepartmentFull>("/departments"),
        fetchAllPages<PositionFull>("/positions"),
      ]);
      employees = loaded[0];
      departments = loaded[1];
      positions = loaded[2];
    } catch {
      // Leave the people sections empty; the rest still loads.
    }
  }

  const active = employees.filter(function (e) {
    return e.status === "active";
  });
  const nameById: Record<string, string> = {};
  for (const e of employees) {
    nameById[e.id] = fullName(e);
    if (e.user_id) result.actors[e.user_id] = fullName(e);
  }
  const departmentOfPosition: Record<string, string> = {};
  for (const p of positions) departmentOfPosition[p.id] = p.department_id;

  if (seesOrg && employees.length > 0) {
    result.activeCount = active.length;
    result.departments = departments.map(function (d) {
      const people = active.filter(function (e) {
        return departmentOfPosition[e.position_id] === d.id;
      });
      return {
        id: d.id,
        name: d.name,
        isCritical: d.is_critical,
        headcount: people.length,
        head: d.head_employee_id && nameById[d.head_employee_id] ? nameById[d.head_employee_id] : "No head set",
      };
    });
    const filled: Record<string, boolean> = {};
    for (const e of active) filled[e.position_id] = true;
    result.vacantCritical = positions.filter(function (p) {
      return p.is_critical && !filled[p.id];
    }).length;
  }

  if (canReadAuditLog(me.role)) {
    const today = todayLocal();
    try {
      const rows = await fetchAllPages<AttendanceRow>("/attendance?date_from=" + today + "&date_to=" + today);
      const seen: Record<string, boolean> = {};
      const nowNames: string[] = [];
      for (const r of rows) {
        seen[r.employee_id] = true;
        if (r.clock_out_at === null) nowNames.push(nameById[r.employee_id] || "An employee");
      }
      result.attendance = { present: Object.keys(seen).length, clockedInNow: nowNames.length, names: nowNames };
    } catch {
      // Leave attendance hidden.
    }
    try {
      const log = await apiFetch<{ data: AuditRow[] }>("/audit-log?limit=8", { method: "GET" });
      result.activity = log.data;
    } catch {
      // Leave activity hidden.
    }
  }

  // Task counts: an employee's own list is only open while clocked in, so a refusal just hides the card.
  const counts = await Promise.all([total("/tasks?status=open&limit=1"), total("/tasks?status=in_progress&limit=1")]);
  result.openTasks = counts[0];
  result.inProgressTasks = counts[1];
  return result;
}

const CARD = "rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl";
const BUTTON = "rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600";

function Stat(props: { label: string; value: string; note: string; tone?: string }) {
  return (
    <div className={CARD}>
      <p className="text-xs uppercase tracking-wide text-gray-500">{props.label}</p>
      <p className={"mt-2 text-2xl font-bold " + (props.tone || "text-white")}>{props.value}</p>
      <p className="mt-1 text-xs text-gray-500">{props.note}</p>
    </div>
  );
}

function DashboardBody() {
  const router = useRouter();
  const state = useLoad<DashboardData>("dashboard", loadDashboard, "Couldn't load the dashboard. Check your connection and try again.");
  const data = state.data;
  const hr = data !== null && isHrRole(data.me.role);

  function actorOf(row: AuditRow): string {
    if (!data || !row.actor_user_id) return "The system";
    if (row.actor_user_id === data.me.userId) return "You";
    return data.actors[row.actor_user_id] || "Someone";
  }

  const stats: { label: string; value: string; note: string; tone?: string }[] = [];
  if (data && data.activeCount !== null) stats.push({ label: "Active employees", value: String(data.activeCount), note: "Across all departments" });
  if (data && data.attendance) {
    stats.push({ label: "Clocked in today", value: String(data.attendance.present), note: data.attendance.clockedInNow + " working right now", tone: "text-emerald-400" });
  }
  if (data && data.openTasks !== null) {
    stats.push({ label: "Open tasks", value: String(data.openTasks), note: (data.inProgressTasks === null ? 0 : data.inProgressTasks) + " in progress" });
  }
  if (data && data.vacantCritical !== null) {
    stats.push({
      label: "Vacant critical roles",
      value: String(data.vacantCritical),
      note: "Critical roles with no active employee",
      tone: data.vacantCritical > 0 ? "text-red-400" : "text-white",
    });
  }

  return (
    <AppShell
      activeLabel="Dashboard"
      title="Dashboard"
      breadcrumb={data && data.me.organization && data.me.organization.name ? data.me.organization.name : undefined}
      userName={data ? data.me.fullName : undefined}
      userRole={data ? roleLabel(data.me.role) : undefined}
      actions={
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={function () { router.push("/workflow/start"); }} className={BUTTON}>
            + Start Workflow
          </button>
          <button type="button" onClick={function () { router.push("/tasks/assign-task"); }} className={BUTTON}>
            + Assign Task
          </button>
          {hr ? (
            <button type="button" onClick={function () { router.push("/employees/invite"); }} className={BUTTON}>
              + Invite Employee
            </button>
          ) : null}
        </div>
      }
    >
      {state.error ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</div>
      ) : null}
      {state.loading ? <p className="text-sm text-gray-400">Loading…</p> : null}

      {data ? (
        <>
          {stats.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {stats.map(function (s) {
                return <Stat key={s.label} label={s.label} value={s.value} note={s.note} tone={s.tone} />;
              })}
            </div>
          ) : (
            <div className={CARD + " text-sm text-gray-400"}>
              Welcome, {data.me.fullName.split(" ")[0] || "there"}. Use <Link href="/tasks" className="text-indigo-400 hover:text-indigo-300">Tasks</Link> and{" "}
              <Link href="/attendance" className="text-indigo-400 hover:text-indigo-300">Attendance</Link> to start your day.
            </div>
          )}

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            {data.attendance ? (
              <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
                <h3 className="text-base font-semibold text-white">Working right now</h3>
                {data.attendance.names.length === 0 ? (
                  <p className="mt-4 text-sm text-gray-500">Nobody is clocked in at the moment.</p>
                ) : (
                  <div className="mt-4 flex flex-col divide-y divide-white/5">
                    {data.attendance.names.map(function (name, i) {
                      return (
                        <div key={name + i} className="flex items-center gap-3 py-2.5">
                          <span className="h-2 w-2 rounded-full bg-emerald-400" />
                          <span className="text-sm font-medium text-white">{name}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
                <Link href="/attendance" className="mt-3 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300">
                  Open attendance &rarr;
                </Link>
              </div>
            ) : null}

            {data.activity ? (
              <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
                <h3 className="text-base font-semibold text-white">Recent workforce activity</h3>
                {data.activity.length === 0 ? (
                  <p className="mt-4 text-sm text-gray-500">Nothing yet. Changes your team makes will show up here.</p>
                ) : (
                  <div className="mt-4 flex flex-col gap-3">
                    {data.activity.map(function (row) {
                      return (
                        <div key={row.id} className="flex items-start gap-3 text-sm">
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                          <span className="text-gray-300">
                            <span className="font-medium text-white">{actorOf(row)}</span> {titleCase(row.action).toLowerCase()}{" "}
                            {titleCase(row.entity_type).toLowerCase()}
                          </span>
                          <span className="ml-auto shrink-0 text-xs text-gray-600">{formatDateTime(row.created_at)}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : null}
          </div>

          {data.departments.length > 0 ? (
            <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold text-white">Departments &amp; headcount</h3>
              <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                      <th className="px-4 py-3 font-medium">Department</th>
                      <th className="px-4 py-3 font-medium">Active employees</th>
                      <th className="px-4 py-3 font-medium">Head</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {data.departments.map(function (d) {
                      return (
                        <tr key={d.id} className="transition hover:bg-white/5">
                          <td className="px-4 py-3 font-medium text-white">
                            {d.name}
                            {d.isCritical ? (
                              <span className="ml-2 rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-medium text-indigo-300">Critical</span>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-gray-300">{d.headcount}</td>
                          <td className="px-4 py-3 text-gray-300">{d.head}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Link href="/organization-structure" className="mt-3 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300">
                View organization &rarr;
              </Link>
            </div>
          ) : null}

          <p className="mt-6 text-xs text-gray-600">
            Leave approvals, payroll and KPI scores will appear here once those modules are live.
          </p>
        </>
      ) : null}
    </AppShell>
  );
}
