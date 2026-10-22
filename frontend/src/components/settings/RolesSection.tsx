"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime, roleLabel } from "@/lib/tasks";
import type { PaginatedResponse } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { SETTINGS_INPUT_CLASS, isHrRole } from "@/lib/settings";
import type { SectionProps } from "./types";

interface MembershipRow {
  id: string;
  role: string;
  is_owner: boolean;
  deactivated_at: string | null;
  created_at: string;
  user: { id: string; email: string; full_name: string };
}

const PAGE_SIZE = 20;
const ROLE_OPTIONS = ["hr_administrator", "business_executive", "manager", "employee"];

// Who can do what, written for people. The server has the last word.
const CAPABILITIES: { label: string; hr: boolean; exec: boolean; manager: boolean; employee: boolean }[] = [
  { label: "Edit company profile and departments", hr: true, exec: false, manager: false, employee: false },
  { label: "Manage team members and roles", hr: true, exec: false, manager: false, employee: false },
  { label: "Set up OKRs and KPIs", hr: true, exec: false, manager: false, employee: false },
  { label: "Review AI suggestions", hr: true, exec: true, manager: false, employee: false },
  { label: "Enter manual KPI scores", hr: true, exec: true, manager: false, employee: false },
  { label: "See the audit log", hr: true, exec: true, manager: false, employee: false },
  { label: "See billing and AI usage", hr: true, exec: false, manager: false, employee: false },
  { label: "Create tasks (managers and department heads, in their scope)", hr: true, exec: false, manager: true, employee: false },
  { label: "Build workflow templates", hr: true, exec: false, manager: true, employee: false },
  { label: "Start a workflow case", hr: true, exec: false, manager: true, employee: true },
  { label: "Work on tasks assigned to them", hr: true, exec: true, manager: true, employee: true },
];

function Tick(props: { on: boolean }) {
  return props.on ? <span className="text-emerald-400">Yes</span> : <span className="text-gray-600">–</span>;
}

export default function RolesSection(props: SectionProps) {
  const canManage = isHrRole(props.me.role);
  const [page, setPage] = useState(1);
  const [reloadCounter, setReloadCounter] = useState(0);
  const state = useLoad<PaginatedResponse<MembershipRow> | null>(
    "members|" + page + "|" + reloadCounter + "|" + canManage,
    async function () {
      if (!canManage) return null;
      return apiFetch<PaginatedResponse<MembershipRow>>("/memberships?page=" + page + "&limit=" + PAGE_SIZE, { method: "GET" });
    },
    "Couldn't load the team."
  );
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  const members = state.data ? state.data.data : [];
  const totalPages = state.data ? state.data.pagination.total_pages : 1;

  async function run(id: string, action: () => Promise<unknown>, failure: string) {
    setError("");
    setBusyId(id);
    try {
      await action();
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : failure);
    } finally {
      setBusyId("");
    }
  }

  function changeRole(m: MembershipRow, role: string) {
    run(m.id, function () {
      return apiFetch("/memberships/" + m.id, { method: "PATCH", body: { role: role } });
    }, "Couldn't change the role. Check your connection and try again.");
  }

  function deactivate(m: MembershipRow) {
    if (!window.confirm("Deactivate " + m.user.full_name + "? They will no longer be able to sign in to this organization.")) return;
    run(m.id, function () {
      return apiFetch("/memberships/" + m.id, { method: "PATCH", body: { is_deactivated: true } });
    }, "Couldn't deactivate that person. Check your connection and try again.");
  }

  function reactivate(m: MembershipRow) {
    run(m.id, function () {
      return apiFetch("/memberships/" + m.id + "/reactivate", { method: "POST", body: {} });
    }, "Couldn't reactivate that person. Check your connection and try again.");
  }

  return (
    <div>
      <h3 className="text-base font-semibold text-white">Roles and permissions</h3>
      <p className="mt-1 text-sm text-gray-500">What each role can do, and who on your team holds which role.</p>

      <div className="mt-6 overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3 font-medium">What they can do</th>
              <th className="px-4 py-3 font-medium">HR Administrator</th>
              <th className="px-4 py-3 font-medium">Business Executive</th>
              <th className="px-4 py-3 font-medium">Manager</th>
              <th className="px-4 py-3 font-medium">Employee</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {CAPABILITIES.map(function (c) {
              return (
                <tr key={c.label}>
                  <td className="px-4 py-3 text-gray-200">{c.label}</td>
                  <td className="px-4 py-3"><Tick on={c.hr} /></td>
                  <td className="px-4 py-3"><Tick on={c.exec} /></td>
                  <td className="px-4 py-3"><Tick on={c.manager} /></td>
                  <td className="px-4 py-3"><Tick on={c.employee} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-gray-500">The system always checks permissions on its side too. Department heads also get task powers inside their own department.</p>

      <div className="mt-10 border-t border-white/10 pt-6">
        <h4 className="text-sm font-semibold text-white">People and access</h4>
        {!canManage ? (
          <p className="mt-3 text-sm text-gray-500">
            Your role is <span className="text-gray-300">{roleLabel(props.me.role)}</span>. Only an HR administrator can see and change who has which role.
          </p>
        ) : (
          <>
            {error ? <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
            {state.loading ? <p className="mt-4 text-sm text-gray-400">Loading…</p> : null}
            {state.error ? <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p> : null}
            {!state.loading && !state.error ? (
              <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="bg-white/5 text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Person</th>
                      <th className="px-4 py-3 font-medium">Role</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {members.map(function (m) {
                      const isSelf = m.user.id === props.me.userId;
                      const deactivated = m.deactivated_at !== null;
                      const locked = isSelf || m.is_owner;
                      return (
                        <tr key={m.id}>
                          <td className="px-4 py-3">
                            <p className="font-medium text-white">
                              {m.user.full_name}
                              {isSelf ? <span className="ml-2 text-xs text-gray-500">(you)</span> : null}
                              {m.is_owner ? <span className="ml-2 rounded bg-indigo-500/15 px-1.5 py-0.5 text-xs text-indigo-300">Owner</span> : null}
                            </p>
                            <p className="text-xs text-gray-500">{m.user.email}</p>
                          </td>
                          <td className="px-4 py-3">
                            <select
                              value={m.role}
                              disabled={locked || deactivated || busyId === m.id}
                              onChange={function (e) {
                                changeRole(m, e.target.value);
                              }}
                              className={SETTINGS_INPUT_CLASS}
                            >
                              {ROLE_OPTIONS.indexOf(m.role) === -1 ? <option value={m.role}>{roleLabel(m.role)}</option> : null}
                              {ROLE_OPTIONS.map(function (r) {
                                return (
                                  <option key={r} value={r}>
                                    {roleLabel(r)}
                                  </option>
                                );
                              })}
                            </select>
                          </td>
                          <td className="px-4 py-3">
                            {deactivated ? (
                              <span className="text-xs text-amber-300">Deactivated {formatDateTime(m.deactivated_at)}</span>
                            ) : (
                              <span className="text-xs text-emerald-400">Active</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {locked ? null : deactivated ? (
                              <button type="button" disabled={busyId === m.id} onClick={function () { reactivate(m); }} className="text-sm font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50">
                                Reactivate
                              </button>
                            ) : (
                              <button type="button" disabled={busyId === m.id} onClick={function () { deactivate(m); }} className="text-sm font-medium text-red-300 hover:text-red-200 disabled:opacity-50">
                                Deactivate
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
            {totalPages > 1 ? (
              <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
                <span>Page {page} of {totalPages}</span>
                <div className="flex gap-2">
                  <button type="button" disabled={page <= 1} onClick={function () { setPage(page - 1); }} className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40">Previous</button>
                  <button type="button" disabled={page >= totalPages} onClick={function () { setPage(page + 1); }} className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40">Next</button>
                </div>
              </div>
            ) : null}
            <p className="mt-3 text-xs text-gray-500">You can&apos;t change your own role, and the account Owner can&apos;t be changed or deactivated.</p>
          </>
        )}
      </div>
    </div>
  );
}
