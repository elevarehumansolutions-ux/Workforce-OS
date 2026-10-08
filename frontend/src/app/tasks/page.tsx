"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import {
  canCreateTasks,
  departmentName,
  employeeName,
  errorMessage,
  formatDateTime,
  isNotClockedIn,
  isPastDue,
  loadCaller,
  roleLabel,
  statusClasses,
  statusLabel,
} from "@/lib/tasks";
import type { CallerContext, PaginatedResponse, Task } from "@/lib/tasks";

type Tab = "mine" | "all";

interface ListResult {
  key: string;
  tasks: Task[];
  total: number;
  totalPages: number;
  error: string;
  notClockedIn: boolean;
}

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "", label: "All (including cancelled)" },
];

export default function TasksPage() {
  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [tabChoice, setTabChoice] = useState<Tab | null>(null);
  const [status, setStatus] = useState("open");
  const [departmentId, setDepartmentId] = useState("");
  const [page, setPage] = useState(1);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [clockingIn, setClockingIn] = useState(false);
  const [clockError, setClockError] = useState("");

  // "My tasks" needs an employee record to filter by; without one the page
  // opens on the full list instead.
  const hasEmployee = ctx !== null && ctx.employee !== null;
  const tab: Tab = tabChoice !== null ? tabChoice : hasEmployee ? "mine" : "all";
  const employeeId = ctx && ctx.employee ? ctx.employee.id : "";

  const key = [tab, status, departmentId, page, reloadCounter, employeeId, ctx ? "ready" : "wait"].join("|");
  const loading = ctx === null ? !ctxError : result === null || result.key !== key;

  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function (err) {
        if (cancelled) return;
        setCtxError(errorMessage(err, "Couldn't load your tasks."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      if (!ctx) return;
      let cancelled = false;
      let path = "/tasks?page=" + page + "&limit=" + PAGE_SIZE;
      if (status) path = path + "&status=" + status;
      if (departmentId) path = path + "&department_id=" + departmentId;
      if (tab === "mine" && employeeId) path = path + "&assigned_to_employee_id=" + employeeId;

      apiFetch<PaginatedResponse<Task>>(path, { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setResult({
            key: key,
            tasks: res.data,
            total: res.pagination.total,
            totalPages: res.pagination.total_pages,
            error: "",
            notClockedIn: false,
          });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            tasks: [],
            total: 0,
            totalPages: 1,
            error: isNotClockedIn(err) ? "" : errorMessage(err, "Couldn't load tasks. Check your connection and try again."),
            notClockedIn: isNotClockedIn(err),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [ctx, tab, status, departmentId, page, employeeId, reloadCounter, key]
  );

  async function clockIn() {
    setClockError("");
    setClockingIn(true);
    try {
      await apiFetch("/attendance/clock-in", { method: "POST" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setClockError(errorMessage(err, "Couldn't clock you in. Check your connection and try again."));
    } finally {
      setClockingIn(false);
    }
  }

  const selectClass =
    "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500";

  const actions =
    ctx && canCreateTasks(ctx) ? (
      <Link
        href="/tasks/assign-task"
        className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
      >
        + Assign task
      </Link>
    ) : null;

  function tabButton(value: Tab, label: string, disabled: boolean) {
    const active = tab === value;
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={function () {
          setTabChoice(value);
          setPage(1);
        }}
        className={
          "rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 " +
          (active ? "bg-indigo-500/15 text-indigo-300" : "text-gray-400 hover:bg-white/5 hover:text-gray-200")
        }
      >
        {label}
      </button>
    );
  }

  return (
    <AppShell
      activeLabel="Tasks"
      title="Tasks"
      breadcrumb="Dashboard > Tasks"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={actions}
    >
      {ctxError ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div>
      ) : null}

      {ctx ? (
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1">
              {tabButton("mine", "My tasks", !hasEmployee)}
              {tabButton("all", "All tasks I can see", false)}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={status}
                onChange={function (e) {
                  setStatus(e.target.value);
                  setPage(1);
                }}
                className={selectClass}
              >
                {STATUS_OPTIONS.map(function (o) {
                  return (
                    <option key={o.label} value={o.value}>
                      {o.label}
                    </option>
                  );
                })}
              </select>
              <select
                value={departmentId}
                onChange={function (e) {
                  setDepartmentId(e.target.value);
                  setPage(1);
                }}
                className={selectClass}
              >
                <option value="">All departments</option>
                {ctx.departments.map(function (d) {
                  return (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          {!hasEmployee ? (
            <p className="mt-3 text-xs text-amber-300">
              Your login isn&apos;t linked to an employee record yet, so there is no &quot;My tasks&quot; list. Ask HR to
              add you as an employee.
            </p>
          ) : null}

          <div className="mt-5">
            {loading ? <p className="text-sm text-gray-400">Loading tasks…</p> : null}

            {!loading && result && result.notClockedIn ? (
              <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-6 text-center">
                <p className="text-base font-semibold">Clock in to see your tasks</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-gray-400">
                  Tasks assigned to you show up once you are clocked in for the day.
                </p>
                {clockError ? <p className="mt-3 text-sm text-red-300">{clockError}</p> : null}
                <button
                  type="button"
                  onClick={clockIn}
                  disabled={clockingIn}
                  className="mt-4 rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {clockingIn ? "Clocking in…" : "Clock in"}
                </button>
              </div>
            ) : null}

            {!loading && result && result.error ? (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {result.error}
              </div>
            ) : null}

            {!loading && result && !result.error && !result.notClockedIn && result.tasks.length === 0 ? (
              <p className="py-6 text-center text-sm text-gray-500">
                No tasks here yet.
                {tab === "all" && status === "open" && !departmentId
                  ? " Tasks assigned to you only appear in this list while you are clocked in."
                  : ""}
              </p>
            ) : null}

            {!loading && result && result.tasks.length > 0 ? (
              <div className="space-y-3">
                {result.tasks.map(function (task) {
                  return (
                    <Link
                      key={task.id}
                      href={"/tasks/" + task.id}
                      className="block rounded-xl border border-white/10 bg-[#0a0e1a] px-5 py-4 transition hover:border-indigo-500/40"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-white">{task.title}</p>
                          <p className="mt-1 text-xs text-gray-500">
                            {departmentName(ctx, task.department_id)} • {employeeName(ctx, task.assigned_to_employee_id)}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          {isPastDue(task) ? (
                            <span className="rounded bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
                              Past due
                            </span>
                          ) : null}
                          <span className={"rounded px-2 py-0.5 text-xs font-medium " + statusClasses(task.status)}>
                            {statusLabel(task.status)}
                          </span>
                          <span className="text-xs text-gray-400">{formatDateTime(task.due_at)}</span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </div>

          {!loading && result && result.totalPages > 1 ? (
            <div className="mt-5 flex items-center justify-between text-sm text-gray-400">
              <button
                type="button"
                disabled={page <= 1}
                onClick={function () {
                  setPage(page - 1);
                }}
                className="rounded-lg border border-white/15 px-4 py-2 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span>
                Page {page} of {result.totalPages} • {result.total} tasks
              </span>
              <button
                type="button"
                disabled={page >= result.totalPages}
                onClick={function () {
                  setPage(page + 1);
                }}
                className="rounded-lg border border-white/15 px-4 py-2 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {!ctx && !ctxError ? <p className="text-sm text-gray-400">Loading…</p> : null}
    </AppShell>
  );
}
