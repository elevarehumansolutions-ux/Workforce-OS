"use client";

import Link from "next/link";
import AppShell from "@/components/AppShell";
import { apiFetch } from "@/lib/api";
import { fetchAllPages, formatDateTime, fullName, roleLabel } from "@/lib/tasks";
import type { Employee, PaginatedResponse } from "@/lib/tasks";
import { canReadAuditLog, loadMe, titleCase } from "@/lib/settings";
import type { MeData } from "@/lib/settings";
import { useLoad } from "@/lib/useLoad";

interface AuditRow {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  created_at: string;
}

interface HubData {
  me: MeData;
  total: number;
  activity: AuditRow[];
  names: Record<string, string>;
}

const ACTION_TEXT: Record<string, string> = {
  create: "added an employee",
  update: "updated an employee",
  delete: "removed an employee",
  offboard: "offboarded an employee",
  reinstate: "reinstated an employee",
  link_user: "linked a login to an employee",
  grant_login: "gave an employee login access",
};

function actionText(row: AuditRow): string {
  return ACTION_TEXT[row.action] || titleCase(row.action).toLowerCase() + " (" + titleCase(row.entity_type).toLowerCase() + ")";
}

async function loadHub(): Promise<HubData> {
  const me = await loadMe();
  const counted = await apiFetch<PaginatedResponse<Employee>>("/employees?limit=1", { method: "GET" });
  let activity: AuditRow[] = [];
  const names: Record<string, string> = {};
  if (canReadAuditLog(me.role)) {
    try {
      const results = await Promise.all([
        apiFetch<{ data: AuditRow[] }>("/audit-log?entity_type=employee&limit=8", { method: "GET" }),
        fetchAllPages<Employee>("/employees"),
      ]);
      activity = results[0].data;
      for (const e of results[1]) {
        if (e.user_id) names[e.user_id] = fullName(e);
      }
    } catch {
      // Recent activity is a nice-to-have; the rest of the page works without it.
    }
  }
  return { me: me, total: counted.pagination.total, activity: activity, names: names };
}

const CARD = "rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40";

export default function EmployeesPage() {
  const state = useLoad<HubData>("employees-hub", loadHub, "Couldn't load this page. Check your connection and try again.");
  const data = state.data;

  function actor(row: AuditRow): string {
    if (!data || !row.actor_user_id) return "The system";
    if (row.actor_user_id === data.me.userId) return "You";
    return data.names[row.actor_user_id] || "Someone";
  }

  return (
    <AppShell
      activeLabel="Employees"
      title="Employees"
      breadcrumb="Dashboard > Employees"
      userName={data ? data.me.fullName : undefined}
      userRole={data ? roleLabel(data.me.role) : undefined}
    >
      {state.error ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <Link href="/employees/directory" className={CARD}>
          <h3 className="text-base font-semibold text-white">Employee Directory</h3>
          <p className="mt-1 text-sm text-gray-500">
            Browse and search all employee records
            {data ? " (" + data.total + (data.total === 1 ? " employee)" : " employees)") : ""}
          </p>
        </Link>
        <Link href="/employees/add" className={CARD}>
          <h3 className="text-base font-semibold text-white">Add Employee</h3>
          <p className="mt-1 text-sm text-gray-500">Onboard a new team member</p>
        </Link>
        <Link href="/employees/critical-roles" className={CARD}>
          <h3 className="text-base font-semibold text-white">Critical Roles</h3>
          <p className="mt-1 text-sm text-gray-500">Roles flagged as critical to your business</p>
        </Link>
        <Link href="/employees/invite" className={CARD}>
          <h3 className="text-base font-semibold text-white">Invite a teammate</h3>
          <p className="mt-1 text-sm text-gray-500">Send a login invite by email</p>
        </Link>
      </div>

      <div className="mt-8 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
        <h3 className="mb-4 text-base font-semibold text-white">Recent Activity</h3>
        {state.loading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : data && !canReadAuditLog(data.me.role) ? (
          <p className="text-sm text-gray-500">Only HR administrators and business executives can see recent activity.</p>
        ) : data && data.activity.length === 0 ? (
          <p className="text-sm text-gray-500">Nothing yet. Changes to employee records will show up here.</p>
        ) : (
          <div className="flex flex-col divide-y divide-white/5">
            {(data ? data.activity : []).map(function (item) {
              return (
                <div key={item.id} className="flex items-center justify-between gap-4 py-3">
                  <p className="text-sm text-gray-300">
                    <span className="font-medium text-white">{actor(item)}</span> {actionText(item)}
                  </p>
                  <span className="flex-shrink-0 text-xs text-gray-600">{formatDateTime(item.created_at)}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
