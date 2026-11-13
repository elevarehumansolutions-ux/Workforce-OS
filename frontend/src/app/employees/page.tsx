"use client";

import Link from "next/link";
import AppShell from "@/components/AppShell";
import { apiFetch } from "@/lib/api";
import { fetchAllPages, formatDateTime, fullName, roleLabel } from "@/lib/tasks";
import type { Employee, PaginatedResponse } from "@/lib/tasks";
import { canReadAuditLog, isHrRole, loadMe } from "@/lib/settings";
import { describeActivity } from "@/lib/activityText";
import type { MeData } from "@/lib/settings";
import { useLoad } from "@/lib/useLoad";

interface AuditRow {
  id: string;
  actor_user_id: string | null;
  actor_name?: string | null;
  subject?: string | null;
  action: string;
  entity_type: string;
  created_at: string;
}

// Someone who can log in but has no employee record yet (they were invited from Invite Team).
interface UnlinkedLogin {
  id: string;
  role: string;
  user: { id: string; email: string; full_name: string };
}

interface HubData {
  me: MeData;
  total: number;
  activity: AuditRow[];
  names: Record<string, string>;
  unlinked: UnlinkedLogin[];
}

function actionText(row: AuditRow): string {
  return describeActivity(row.action, row.entity_type, row.subject);
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
  // HR only: logins that have no employee record, so nobody has to remember who was invited.
  let unlinked: UnlinkedLogin[] = [];
  if (isHrRole(me.role)) {
    try {
      unlinked = await fetchAllPages<UnlinkedLogin>("/employees/unlinked-members");
    } catch {
      // The list is a convenience; the rest of the page works without it.
    }
  }
  return { me: me, total: counted.pagination.total, activity: activity, names: names, unlinked: unlinked };
}

const CARD = "rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40";

export default function EmployeesPage() {
  const state = useLoad<HubData>("employees-hub", loadHub, "Couldn't load this page. Check your connection and try again.");
  const data = state.data;

  function actor(row: AuditRow): string {
    if (!data || !row.actor_user_id) return "The system";
    if (row.actor_user_id === data.me.userId) return "You";
    return row.actor_name || data.names[row.actor_user_id] || "Someone";
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
        {data && data.me.role === "hr_administrator" ? (
          <Link href="/employees/add" className={CARD}>
            <h3 className="text-base font-semibold text-white">Add Employee</h3>
            <p className="mt-1 text-sm text-gray-500">Onboard a new team member</p>
          </Link>
        ) : null}
        <Link href="/employees/chart" className={CARD}>
          <h3 className="text-base font-semibold text-white">Org chart</h3>
          <p className="mt-1 text-sm text-gray-500">Every role with the people in it, and who is vacant</p>
        </Link>
        <Link href="/employees/critical-roles" className={CARD}>
          <h3 className="text-base font-semibold text-white">Critical Roles</h3>
          <p className="mt-1 text-sm text-gray-500">Roles flagged as critical to your business</p>
        </Link>
        {data && data.me.role === "hr_administrator" ? (
          <Link href="/employees/invite" className={CARD}>
            <h3 className="text-base font-semibold text-white">Invite a teammate</h3>
            <p className="mt-1 text-sm text-gray-500">Send a login invite by email</p>
          </Link>
        ) : null}
      </div>

      {data && data.unlinked.length > 0 ? (
        <div className="mt-8 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-6 shadow-xl">
          <h3 className="text-base font-semibold text-white">
            {data.unlinked.length} {data.unlinked.length === 1 ? "person has" : "people have"} a login but no employee record
          </h3>
          <p className="mt-1 text-sm text-gray-400">
            They were invited to the system, so they can sign in, but they are not in the directory, on the org chart,
            or in any department yet. Create their record: the form opens with their name and email filled in and the
            login already linked.
          </p>
          <div className="mt-4 space-y-2">
            {data.unlinked.map(function (login) {
              return (
                <div
                  key={login.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                >
                  <p className="text-sm text-gray-200">
                    <span className="font-medium text-white">{login.user.full_name}</span>{" "}
                    <span className="text-gray-500">{login.user.email}, {roleLabel(login.role)}</span>
                  </p>
                  <Link
                    href={"/employees/add?member=" + login.user.id}
                    className="rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-600"
                  >
                    Create employee record
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

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
