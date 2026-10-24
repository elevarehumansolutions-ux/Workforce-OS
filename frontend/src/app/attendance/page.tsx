"use client";

import { useState } from "react";
import AppShell from "@/components/AppShell";
import { ApiError, apiFetch } from "@/lib/api";
import { errorMessage, formatDuration, fullName, loadCaller, roleLabel } from "@/lib/tasks";
import type { PaginatedResponse } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";

interface AttendanceRecord {
  id: string;
  employee_id: string;
  clock_in_at: string;
  clock_out_at: string | null;
  closed_by: "employee" | "system" | null;
  close_reason: string | null;
}

interface ClockInResult {
  already_clocked_in: boolean;
  record: AttendanceRecord;
}

const PAGE_SIZE = 20;

const INPUT_CLASS =
  "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500";

function formatDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function hoursWorked(record: AttendanceRecord): string {
  if (!record.clock_out_at) return "In progress";
  const seconds = (new Date(record.clock_out_at).getTime() - new Date(record.clock_in_at).getTime()) / 1000;
  return formatDuration(seconds);
}

function statusBadge(record: AttendanceRecord) {
  if (!record.clock_out_at) {
    return <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">Clocked in</span>;
  }
  if (record.closed_by === "system") {
    return <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300">Auto-closed</span>;
  }
  return <span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-medium text-gray-300">Clocked out</span>;
}

export default function AttendancePage() {
  const ctxState = useLoad("attendance-ctx", loadCaller, "Couldn't load your account. Check your connection and try again.");
  const ctx = ctxState.data;

  const [reloadCounter, setReloadCounter] = useState(0);
  const [employeeId, setEmployeeId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");

  const rangeInvalid = dateFrom !== "" && dateTo !== "" && dateFrom > dateTo;

  // Whether the caller is clocked in right now: their newest record is still open.
  const current = useLoad<AttendanceRecord | null>(
    "attendance-current|" + reloadCounter,
    async function () {
      const res = await apiFetch<PaginatedResponse<AttendanceRecord>>("/attendance?limit=1", { method: "GET" });
      const first = res.data.length > 0 ? res.data[0] : null;
      return first && !first.clock_out_at ? first : null;
    },
    "Couldn't check your attendance."
  );
  const noProfile = current.status === 409;
  const clockedIn = current.data !== null;

  const history = useLoad<PaginatedResponse<AttendanceRecord>>(
    ["attendance-history", reloadCounter, employeeId, dateFrom, dateTo, page, rangeInvalid].join("|"),
    async function () {
      if (rangeInvalid) {
        return {
          data: [],
          pagination: { page: 1, limit: PAGE_SIZE, total: 0, total_pages: 1, has_next: false, has_previous: false },
        };
      }
      const params = ["page=" + page, "limit=" + PAGE_SIZE];
      if (employeeId) params.push("employee_id=" + employeeId);
      if (dateFrom) params.push("date_from=" + dateFrom);
      if (dateTo) params.push("date_to=" + dateTo);
      return apiFetch<PaginatedResponse<AttendanceRecord>>("/attendance?" + params.join("&"), { method: "GET" });
    },
    "Couldn't load attendance. Check your connection and try again."
  );

  const canSeeOthers = ctx !== null && (ctx.role === "hr_administrator" || ctx.role === "business_executive");
  const rows = history.data ? history.data.data : [];
  const totalPages = history.data ? history.data.pagination.total_pages : 1;
  const total = history.data ? history.data.pagination.total : 0;

  async function clockIn() {
    setActionError("");
    setNotice("");
    setBusy(true);
    try {
      const res = await apiFetch<ClockInResult>("/attendance/clock-in", { method: "POST" });
      if (res.already_clocked_in) setNotice("You were already clocked in, so nothing changed.");
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setActionError(errorMessage(err, "Couldn't clock you in. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  async function clockOut() {
    setActionError("");
    setNotice("");
    setBusy(true);
    try {
      await apiFetch("/attendance/clock-out", { method: "POST" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      if (err instanceof ApiError && err.code === "NOT_CLOCKED_IN") {
        setNotice("You are not clocked in. The list has been refreshed.");
        setReloadCounter(reloadCounter + 1);
      } else {
        setActionError(errorMessage(err, "Couldn't clock you out. Check your connection and try again."));
      }
    } finally {
      setBusy(false);
    }
  }

  function chooseEmployee(value: string) {
    setEmployeeId(value);
    setPage(1);
  }

  const viewingOwn = employeeId === "";

  return (
    <AppShell
      activeLabel="Attendance"
      title="Attendance"
      breadcrumb="Dashboard > Attendance"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
    >
      {ctxState.error ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{ctxState.error}</div>
      ) : null}

      <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
        <p className="text-xs uppercase tracking-wide text-gray-500">Your day</p>
        {current.loading ? (
          <p className="mt-3 text-sm text-gray-400">Checking…</p>
        ) : noProfile ? (
          <p className="mt-3 text-sm text-gray-300">
            Your account isn&apos;t linked to an employee record yet, so you can&apos;t clock in. Ask your HR administrator to add you as an employee.
          </p>
        ) : current.error ? (
          <p className="mt-3 text-sm text-red-300">{current.error}</p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-lg font-semibold text-white">{clockedIn ? "You are clocked in" : "You are not clocked in"}</p>
              {current.data ? (
                <p className="mt-0.5 text-sm text-gray-400">Since {formatClock(current.data.clock_in_at)} on {formatDay(current.data.clock_in_at)}</p>
              ) : (
                <p className="mt-0.5 text-sm text-gray-400">Clock in to start your day and see the tasks assigned to you.</p>
              )}
            </div>
            {clockedIn ? (
              <button
                type="button"
                disabled={busy}
                onClick={clockOut}
                className="rounded-lg border border-red-500/40 px-5 py-2.5 text-sm font-semibold text-red-300 hover:bg-red-500/10 disabled:opacity-50"
              >
                {busy ? "Working…" : "Clock out"}
              </button>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={clockIn}
                className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
              >
                {busy ? "Working…" : "Clock in"}
              </button>
            )}
          </div>
        )}
        {actionError ? <p className="mt-3 text-sm text-red-300">{actionError}</p> : null}
        {notice ? <p className="mt-3 text-sm text-gray-300">{notice}</p> : null}
      </div>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        {canSeeOthers && ctx ? (
          <div>
            <label className="mb-1 block text-xs text-gray-500">Whose attendance</label>
            <select value={employeeId} onChange={function (e) { chooseEmployee(e.target.value); }} className={INPUT_CLASS}>
              <option value="">My attendance</option>
              {ctx.employees.map(function (e) {
                return (
                  <option key={e.id} value={e.id}>
                    {fullName(e)}
                    {e.status === "inactive" ? " (inactive)" : ""}
                  </option>
                );
              })}
            </select>
          </div>
        ) : null}
        <div>
          <label className="mb-1 block text-xs text-gray-500">From</label>
          <input type="date" value={dateFrom} onChange={function (e) { setDateFrom(e.target.value); setPage(1); }} className={INPUT_CLASS} />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">To</label>
          <input type="date" value={dateTo} onChange={function (e) { setDateTo(e.target.value); setPage(1); }} className={INPUT_CLASS} />
        </div>
        {dateFrom || dateTo ? (
          <button
            type="button"
            onClick={function () { setDateFrom(""); setDateTo(""); setPage(1); }}
            className="pb-2 text-sm text-indigo-400 hover:text-indigo-300"
          >
            Clear dates
          </button>
        ) : null}
      </div>

      {rangeInvalid ? <p className="mt-3 text-sm text-amber-300">The &quot;From&quot; date is after the &quot;To&quot; date.</p> : null}

      <div className="mt-4 overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
        {history.loading ? (
          <p className="p-10 text-center text-sm text-gray-500">Loading…</p>
        ) : history.error ? (
          <p className="p-10 text-center text-sm text-red-300">
            {history.status === 409 ? "Your account isn't linked to an employee record yet, so there is no attendance to show." : history.error}
          </p>
        ) : rows.length === 0 ? (
          <p className="p-10 text-center text-sm text-gray-500">
            {viewingOwn ? "No attendance records yet. Clock in to create your first one." : "No attendance records for this person in this period."}
          </p>
        ) : (
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                <th className="px-6 py-3 font-medium">Date</th>
                <th className="px-6 py-3 font-medium">Clock in</th>
                <th className="px-6 py-3 font-medium">Clock out</th>
                <th className="px-6 py-3 font-medium">Time worked</th>
                <th className="px-6 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map(function (r) {
                return (
                  <tr key={r.id} className="hover:bg-white/5">
                    <td className="px-6 py-4 font-medium text-white">{formatDay(r.clock_in_at)}</td>
                    <td className="px-6 py-4 text-gray-300">{formatClock(r.clock_in_at)}</td>
                    <td className="px-6 py-4 text-gray-300">{r.clock_out_at ? formatClock(r.clock_out_at) : "-"}</td>
                    <td className="px-6 py-4 text-gray-300">{hoursWorked(r)}</td>
                    <td className="px-6 py-4">
                      {statusBadge(r)}
                      {r.closed_by === "system" ? (
                        <p className="mt-1 max-w-[220px] text-xs text-gray-500">
                          {r.close_reason || "Did not clock out"}. The time shown is the midnight cutoff, not when they left.
                        </p>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 ? (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {page} of {totalPages} · {total} records
          </span>
          <div className="flex gap-2">
            <button type="button" disabled={page <= 1} onClick={function () { setPage(page - 1); }} className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40">
              Previous
            </button>
            <button type="button" disabled={page >= totalPages} onClick={function () { setPage(page + 1); }} className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40">
              Next
            </button>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
