"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import {
  BLOCK_CATEGORY_OPTIONS,
  activeEmployees,
  blockCategoryLabel,
  canBlockTask,
  canCancelTask,
  canCompleteTask,
  canEditTask,
  canReassignTask,
  canUnblockTask,
  departmentName,
  employeeName,
  errorMessage,
  formatDateTime,
  formatDuration,
  fullName,
  isNotClockedIn,
  isoToLocalInput,
  loadCaller,
  localInputToIso,
  reviewStatusClasses,
  reviewStatusLabel,
  roleLabel,
  statusClasses,
  statusLabel,
} from "@/lib/tasks";
import type { BlockCategory, CallerContext, Task, TaskBlock } from "@/lib/tasks";

type Panel = "edit" | "cancel" | "reassign" | "block" | null;

interface TaskResult {
  key: string;
  task: Task | null;
  error: string;
  notClockedIn: boolean;
}

interface BlocksResult {
  key: string;
  blocks: TaskBlock[];
  error: string;
}

const inputClass =
  "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500";

function TaskDetailContent() {
  const params = useParams<{ id: string }>();
  // The "Was something holding up this task?" notification opens the task
  // with ?action=block so the Mark blocked form is ready.
  const searchParams = useSearchParams();
  const taskId = params.id;

  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<TaskResult | null>(null);

  const [panel, setPanel] = useState<Panel>(searchParams.get("action") === "block" ? "block" : null);
  const [blocksResult, setBlocksResult] = useState<BlocksResult | null>(null);
  const [blockCategory, setBlockCategory] = useState<BlockCategory>("awaiting_approval");
  const [blockReason, setBlockReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [clockingIn, setClockingIn] = useState(false);

  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editDue, setEditDue] = useState("");
  const [editKpi, setEditKpi] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [reassignTo, setReassignTo] = useState("");
  const [reassignDue, setReassignDue] = useState("");

  const key = taskId + "|" + reloadCounter;
  const loading = result === null || result.key !== key;
  const task = result && result.key === key ? result.task : null;

  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function (err) {
        if (cancelled) return;
        setCtxError(errorMessage(err, "Couldn't load this task. Check your connection and try again."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      let cancelled = false;
      apiFetch<Task>("/tasks/" + taskId, { method: "GET" })
        .then(function (loaded) {
          if (cancelled) return;
          setResult({ key: key, task: loaded, error: "", notClockedIn: false });
        })
        .catch(function (err) {
          if (cancelled) return;
          const notFound = err instanceof ApiError && err.status === 404;
          setResult({
            key: key,
            task: null,
            error: isNotClockedIn(err)
              ? ""
              : notFound
                ? "This task doesn't exist, or you don't have access to it."
                : errorMessage(err, "Couldn't load this task. Check your connection and try again."),
            notClockedIn: isNotClockedIn(err),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [taskId, key]
  );

  useEffect(
    function () {
      let cancelled = false;
      apiFetch<TaskBlock[]>("/tasks/" + taskId + "/blocks", { method: "GET" })
        .then(function (list) {
          if (cancelled) return;
          setBlocksResult({ key: key, blocks: list, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          // The history is a nice-to-have; the task itself still shows.
          setBlocksResult({ key: key, blocks: [], error: isNotClockedIn(err) ? "" : errorMessage(err, "Couldn't load the block history.") });
        });
      return function () {
        cancelled = true;
      };
    },
    [taskId, key]
  );

  function reload() {
    setReloadCounter(reloadCounter + 1);
  }

  function closePanel() {
    setPanel(null);
    setActionError("");
  }

  function applyUpdated(updated: Task, message: string) {
    setResult({ key: key, task: updated, error: "", notClockedIn: false });
    setNotice(message);
    setPanel(null);
    setActionError("");
  }

  // 404 / 409 here mean the task moved on without this page knowing
  // (completed or cancelled elsewhere, reassigned at the same moment), so
  // show the server's wording and reload to match it.
  function handleFailure(err: unknown, fallback: string) {
    setActionError(errorMessage(err, fallback));
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      setPanel(null);
      reload();
    }
  }

  async function clockIn() {
    setActionError("");
    setClockingIn(true);
    try {
      await apiFetch("/attendance/clock-in", { method: "POST" });
      reload();
    } catch (err) {
      setActionError(errorMessage(err, "Couldn't clock you in. Check your connection and try again."));
    } finally {
      setClockingIn(false);
    }
  }

  async function complete() {
    if (!task) return;
    setNotice("");
    setActionError("");
    setBusy(true);
    try {
      const updated = await apiFetch<Task>("/tasks/" + task.id + "/complete", { method: "POST" });
      applyUpdated(updated, "Task marked as completed.");
    } catch (err) {
      handleFailure(err, "Couldn't complete the task. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function openEdit() {
    if (!task) return;
    setNotice("");
    setActionError("");
    setEditTitle(task.title);
    setEditDescription(task.description || "");
    setEditDue(isoToLocalInput(task.due_at));
    setEditKpi(task.kpi_id || "");
    setPanel("edit");
  }

  async function saveEdit() {
    if (!task) return;
    setActionError("");
    const body: Record<string, string | null> = {};
    const trimmedTitle = editTitle.trim();
    if (!trimmedTitle) {
      setActionError("The title can't be empty.");
      return;
    }
    if (trimmedTitle !== task.title) body.title = trimmedTitle;
    if (editDescription.trim() !== (task.description || "")) body.description = editDescription.trim();
    if (editDue !== isoToLocalInput(task.due_at)) {
      const iso = localInputToIso(editDue);
      if (editDue && !iso) {
        setActionError("That deadline isn't a valid date and time.");
        return;
      }
      body.due_at = iso;
    }
    if (editKpi !== (task.kpi_id || "")) body.kpi_id = editKpi ? editKpi : null;
    if (Object.keys(body).length === 0) {
      setActionError("Change something first, or press Cancel.");
      return;
    }

    setBusy(true);
    try {
      const updated = await apiFetch<Task>("/tasks/" + task.id, { method: "PATCH", body: body });
      applyUpdated(updated, "Task updated.");
    } catch (err) {
      handleFailure(err, "Couldn't save your changes. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function openCancel() {
    setNotice("");
    setActionError("");
    setCancelReason("");
    setPanel("cancel");
  }

  async function confirmCancel() {
    if (!task) return;
    setActionError("");
    const reason = cancelReason.trim();
    if (!reason) {
      setActionError("Give a reason for cancelling. The assignee will see it.");
      return;
    }
    if (reason.length > 500) {
      setActionError("The reason can be at most 500 characters.");
      return;
    }
    setBusy(true);
    try {
      const updated = await apiFetch<Task>("/tasks/" + task.id + "/cancel", {
        method: "POST",
        body: { reason: reason },
      });
      applyUpdated(updated, "Task cancelled.");
    } catch (err) {
      handleFailure(err, "Couldn't cancel the task. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function openReassign() {
    setNotice("");
    setActionError("");
    setReassignTo("");
    setReassignDue("");
    setPanel("reassign");
  }

  async function confirmReassign() {
    if (!task) return;
    setActionError("");
    if (!reassignTo) {
      setActionError("Choose who the task goes to.");
      return;
    }
    const iso = localInputToIso(reassignDue);
    if (!iso) {
      setActionError("Set a new deadline. The new person gets a fresh clock.");
      return;
    }
    if (new Date(iso).getTime() <= new Date().getTime()) {
      setActionError("The new deadline has to be in the future.");
      return;
    }
    setBusy(true);
    try {
      const updated = await apiFetch<Task>("/tasks/" + task.id + "/reassign", {
        method: "POST",
        body: { assigned_to_employee_id: reassignTo, due_at: iso },
      });
      applyUpdated(updated, "Task " + (task.assigned_to_employee_id ? "reassigned" : "assigned") + ".");
    } catch (err) {
      handleFailure(err, "Couldn't reassign the task. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function openBlock() {
    setNotice("");
    setActionError("");
    setBlockCategory("awaiting_approval");
    setBlockReason("");
    setPanel("block");
  }

  async function confirmBlock() {
    if (!task) return;
    setActionError("");
    const reason = blockReason.trim();
    if (!reason) {
      setActionError("Say what is holding the task up.");
      return;
    }
    if (reason.length > 500) {
      setActionError("The reason can be at most 500 characters.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/tasks/" + task.id + "/block", {
        method: "POST",
        body: { category: blockCategory, reason: reason },
      });
      setPanel(null);
      setNotice("Task marked as blocked. Someone will review it.");
      reload();
    } catch (err) {
      handleFailure(err, "Couldn't mark the task as blocked. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function unblock() {
    if (!task) return;
    setNotice("");
    setActionError("");
    setBusy(true);
    try {
      await apiFetch("/tasks/" + task.id + "/unblock", { method: "POST" });
      setNotice("Task unblocked.");
      reload();
    } catch (err) {
      handleFailure(err, "Couldn't unblock the task. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  const blocks = blocksResult && blocksResult.key === key ? blocksResult.blocks : [];
  const blocksError = blocksResult && blocksResult.key === key ? blocksResult.error : "";

  const isActive = task !== null && (task.status === "open" || task.status === "in_progress");
  const kpiName =
    ctx && task && task.kpi_id
      ? (ctx.kpis.find(function (k) {
          return k.id === task.kpi_id;
        }) || { name: "Linked KPI" }).name
      : "";

  const buttonClass =
    "rounded-lg border px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ";

  return (
    <AppShell
      activeLabel="Tasks"
      title="Task"
      breadcrumb="Dashboard > Tasks > Task"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/tasks" className="text-sm font-medium text-gray-400 hover:text-gray-200">
          Back to tasks
        </Link>
      }
    >
      {ctxError ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div>
      ) : null}
      {(loading || !ctx) && !ctxError ? <p className="text-sm text-gray-400">Loading…</p> : null}

      {!loading && result && result.notClockedIn ? (
        <div className="max-w-xl rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-6 text-center">
          <p className="text-base font-semibold">Clock in to see this task</p>
          <p className="mt-1 text-sm text-gray-400">Tasks assigned to you show up once you are clocked in for the day.</p>
          {actionError ? <p className="mt-3 text-sm text-red-300">{actionError}</p> : null}
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
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{result.error}</div>
      ) : null}

      {ctx && task ? (
        <div className="max-w-3xl space-y-5">
          {notice ? (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
              {notice}
            </div>
          ) : null}
          {actionError && panel === null ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {actionError}
            </div>
          ) : null}

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <h2 className="text-xl font-bold">{task.title}</h2>
              <div className="flex items-center gap-2">
                {task.overdue ? (
                  <span className="rounded bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">Overdue</span>
                ) : null}
                {task.blocked_since ? (
                  <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-300">Blocked</span>
                ) : null}
                <span className={"rounded px-2 py-0.5 text-xs font-medium " + statusClasses(task.status)}>
                  {statusLabel(task.status)}
                </span>
              </div>
            </div>

            {task.description ? <p className="mt-4 whitespace-pre-wrap text-sm text-gray-300">{task.description}</p> : null}

            <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-gray-500">Department</dt>
                <dd className="mt-0.5 text-gray-200">{departmentName(ctx, task.department_id)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Assigned to</dt>
                <dd className="mt-0.5 text-gray-200">
                  {employeeName(ctx, task.assigned_to_employee_id)}
                  {!task.assigned_to_employee_id && isActive ? (
                    <span className="block text-xs text-amber-300">This task needs an owner.</span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Deadline</dt>
                <dd className="mt-0.5 text-gray-200">
                  {formatDateTime(task.due_at)}
                  {task.due_at && task.approved_blocked_seconds > 0 ? (
                    <span className="block text-xs text-gray-500">
                      Extended by {formatDuration(task.approved_blocked_seconds)} for approved blocks
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Linked KPI</dt>
                <dd className="mt-0.5 text-gray-200">{kpiName || "None"}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Created</dt>
                <dd className="mt-0.5 text-gray-200">{formatDateTime(task.created_at)}</dd>
              </div>
              {task.completed_at ? (
                <div>
                  <dt className="text-xs text-gray-500">Completed</dt>
                  <dd className="mt-0.5 text-gray-200">{formatDateTime(task.completed_at)}</dd>
                </div>
              ) : null}
            </dl>

            {task.blocked_since ? (
              <div className="mt-6 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                Blocked since {formatDateTime(task.blocked_since)}. A blocked task is never counted as overdue.
              </div>
            ) : null}

            {task.status === "cancelled" ? (
              <div className="mt-6 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm">
                <p className="text-xs text-gray-500">Why it was cancelled</p>
                <p className="mt-1 whitespace-pre-wrap text-gray-200">{task.cancel_reason || "No reason recorded."}</p>
              </div>
            ) : null}

            {isActive ? (
              <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-white/10 pt-5">
                {canBlockTask(ctx, task) ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={openBlock}
                    className={buttonClass + "border-amber-500/40 text-amber-300 hover:bg-amber-500/10"}
                  >
                    Mark blocked
                  </button>
                ) : null}
                {canUnblockTask(ctx, task) ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={unblock}
                    className={buttonClass + "border-amber-500/40 text-amber-300 hover:bg-amber-500/10"}
                  >
                    Unblock
                  </button>
                ) : null}
                {canCompleteTask(ctx, task) ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={complete}
                    className={buttonClass + "border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10"}
                  >
                    {busy && panel === null ? "Saving…" : "Mark complete"}
                  </button>
                ) : null}
                {canEditTask(ctx, task) ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={openEdit}
                    className={buttonClass + "border-white/15 text-white hover:bg-white/5"}
                  >
                    Edit
                  </button>
                ) : null}
                {canReassignTask(ctx, task) ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={openReassign}
                    className={buttonClass + "border-white/15 text-white hover:bg-white/5"}
                  >
                    {task.assigned_to_employee_id ? "Reassign" : "Assign"}
                  </button>
                ) : null}
                {canCancelTask(ctx, task) ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={openCancel}
                    className={buttonClass + "border-red-500/40 text-red-400 hover:bg-red-500/10"}
                  >
                    Cancel task
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          {panel === "block" && canBlockTask(ctx, task) ? (
            <div className="space-y-4 rounded-2xl border border-amber-500/30 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold">Mark this task as blocked</h3>
              <p className="text-sm text-gray-400">
                Use this when something outside your hands is stopping the work. While it is blocked the task isn&apos;t
                counted as overdue. A reviewer then decides whether the time counts, and only an approved block gives the
                time back.
              </p>
              {actionError ? <p className="text-sm text-red-300">{actionError}</p> : null}
              <div>
                <label className="mb-1 block text-xs text-gray-500">What is it waiting on?</label>
                <select
                  value={blockCategory}
                  onChange={function (e) {
                    setBlockCategory(e.target.value as BlockCategory);
                  }}
                  className={inputClass}
                >
                  {BLOCK_CATEGORY_OPTIONS.map(function (o) {
                    return (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    );
                  })}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">Explain (required)</label>
                <textarea
                  rows={3}
                  maxLength={500}
                  value={blockReason}
                  onChange={function (e) {
                    setBlockReason(e.target.value);
                  }}
                  className={inputClass}
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={confirmBlock}
                  className="rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-black hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? "Saving…" : "Mark blocked"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={closePanel}
                  className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {panel === "edit" ? (
            <div className="space-y-4 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold">Edit task</h3>
              {actionError ? <p className="text-sm text-red-300">{actionError}</p> : null}
              <div>
                <label className="mb-1 block text-xs text-gray-500">Title</label>
                <input
                  type="text"
                  value={editTitle}
                  onChange={function (e) {
                    setEditTitle(e.target.value);
                  }}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">Description</label>
                <textarea
                  rows={4}
                  value={editDescription}
                  onChange={function (e) {
                    setEditDescription(e.target.value);
                  }}
                  className={inputClass}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Deadline</label>
                  <input
                    type="datetime-local"
                    value={editDue}
                    onChange={function (e) {
                      setEditDue(e.target.value);
                    }}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Linked KPI</label>
                  <select
                    value={editKpi}
                    onChange={function (e) {
                      setEditKpi(e.target.value);
                    }}
                    className={inputClass}
                  >
                    <option value="">No linked KPI</option>
                    {ctx.kpis.map(function (k) {
                      return (
                        <option key={k.id} value={k.id}>
                          {k.name} ({departmentName(ctx, k.department_id)})
                        </option>
                      );
                    })}
                  </select>
                </div>
              </div>
              <p className="text-xs text-gray-500">To change who the task is assigned to, use Reassign.</p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={saveEdit}
                  className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? "Saving…" : "Save changes"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={closePanel}
                  className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {panel === "cancel" ? (
            <div className="space-y-4 rounded-2xl border border-red-500/30 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold">Cancel this task?</h3>
              <p className="text-sm text-gray-400">
                This can&apos;t be undone. The person it&apos;s assigned to will be told, along with your reason.
              </p>
              {actionError ? <p className="text-sm text-red-300">{actionError}</p> : null}
              <div>
                <label className="mb-1 block text-xs text-gray-500">Reason (required)</label>
                <textarea
                  rows={3}
                  maxLength={500}
                  value={cancelReason}
                  onChange={function (e) {
                    setCancelReason(e.target.value);
                  }}
                  className={inputClass}
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={confirmCancel}
                  className="rounded-lg bg-red-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? "Cancelling…" : "Cancel task"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={closePanel}
                  className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5"
                >
                  Keep task
                </button>
              </div>
            </div>
          ) : null}

          {panel === "reassign" ? (
            <div className="space-y-4 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold">
                {task.assigned_to_employee_id ? "Reassign task" : "Assign task"}
              </h3>
              {actionError ? <p className="text-sm text-red-300">{actionError}</p> : null}
              {task.blocked_since ? (
                <p className="text-xs text-gray-500">Reassigning ends the current block, and the new person starts fresh.</p>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Assign to</label>
                  <select
                    value={reassignTo}
                    onChange={function (e) {
                      setReassignTo(e.target.value);
                    }}
                    className={inputClass}
                  >
                    <option value="">Select person…</option>
                    {activeEmployees(ctx)
                      .filter(function (emp) {
                        return emp.id !== task.assigned_to_employee_id;
                      })
                      .map(function (emp) {
                        return (
                          <option key={emp.id} value={emp.id}>
                            {fullName(emp)}
                          </option>
                        );
                      })}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-gray-500">New deadline (required)</label>
                  <input
                    type="datetime-local"
                    value={reassignDue}
                    onChange={function (e) {
                      setReassignDue(e.target.value);
                    }}
                    className={inputClass}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={confirmReassign}
                  className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? "Saving…" : task.assigned_to_employee_id ? "Reassign" : "Assign"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={closePanel}
                  className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {blocks.length > 0 || blocksError ? (
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold">Block history</h3>
              {blocksError ? <p className="mt-2 text-sm text-gray-500">{blocksError}</p> : null}
              <div className="mt-3 space-y-3">
                {blocks.map(function (b) {
                  return (
                    <div key={b.id} className="rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-gray-200">{blockCategoryLabel(b.category)}</span>
                        <span className={"rounded px-2 py-0.5 text-xs font-medium " + reviewStatusClasses(b.review_status)}>
                          {reviewStatusLabel(b.review_status)}
                        </span>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-gray-400">{b.reason}</p>
                      <p className="mt-1 text-xs text-gray-500">
                        {formatDateTime(b.blocked_at)} to {b.unblocked_at ? formatDateTime(b.unblocked_at) : "still blocked"}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </AppShell>
  );
}

export default function TaskDetailPage() {
  // useSearchParams() needs a Suspense boundary in the App Router.
  return (
    <Suspense fallback={null}>
      <TaskDetailContent />
    </Suspense>
  );
}
