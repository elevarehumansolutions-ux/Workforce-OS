"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { departmentName, employeeName, errorMessage, formatDateTime, loadCaller, roleLabel, statusLabel } from "@/lib/tasks";
import type { CallerContext } from "@/lib/tasks";
import { canCancelCase, caseStatusClasses, caseStatusLabel, stepState, stepStateClasses, stepStateLabel, taskForStep } from "@/lib/workflow";
import type { CaseDetail, CaseTask, WorkflowTemplate } from "@/lib/workflow";

interface CaseResult {
  key: string;
  detail: CaseDetail | null;
  templateName: string;
  error: string;
}

function CaseDetailContent() {
  const searchParams = useSearchParams();
  const caseId = searchParams.get("id") || "";

  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<CaseResult | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  const key = [caseId, reloadCounter].join("|");
  const loading = caseId !== "" && (result === null || result.key !== key);

  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function (err) {
        if (cancelled) return;
        setCtxError(errorMessage(err, "Couldn't load this page."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      if (!caseId) return;
      let cancelled = false;
      apiFetch<CaseDetail>("/workflow-instances/" + caseId, { method: "GET" })
        .then(function (detail) {
          // The template name is nice to have; the case is shown even if it can't be read.
          return apiFetch<WorkflowTemplate>("/workflow-templates/" + detail.workflow_template_id, { method: "GET" })
            .then(function (t) {
              return { detail: detail, templateName: t.name };
            })
            .catch(function () {
              return { detail: detail, templateName: "" };
            });
        })
        .then(function (res) {
          if (cancelled) return;
          setResult({ key: key, detail: res.detail, templateName: res.templateName, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            detail: null,
            templateName: "",
            error:
              err instanceof ApiError && err.code === "WORKFLOW_INSTANCE_NOT_FOUND"
                ? "This case wasn't found, or you can't see it."
                : errorMessage(err, "Couldn't load this case. Check your connection and try again."),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [caseId, key]
  );

  async function confirmCancel() {
    if (!result || !result.detail) return;
    const trimmed = reason.trim();
    if (!trimmed) {
      setActionError("Give a reason for cancelling.");
      return;
    }
    setBusy(true);
    setActionError("");
    try {
      await apiFetch("/workflow-instances/" + result.detail.id + "/cancel", { method: "POST", body: { reason: trimmed } });
      setCancelling(false);
      setReason("");
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      if (err instanceof ApiError && err.code === "WORKFLOW_INSTANCE_NOT_IN_PROGRESS") {
        // Already finished or cancelled by someone else: show the current state.
        setActionError(err.message);
        setCancelling(false);
        setReloadCounter(reloadCounter + 1);
      } else {
        setActionError(errorMessage(err, "Couldn't cancel this case. Check your connection and try again."));
      }
    } finally {
      setBusy(false);
    }
  }

  const detail = result ? result.detail : null;

  // Progress: steps with a finished (or skipped) task are passed, the one with an open task is current.
  let passed = 0;
  if (detail) {
    for (const s of detail.steps) {
      const st = stepState(taskForStep(s, detail.tasks));
      if (st === "done" || st === "skipped") passed = passed + 1;
    }
  }
  const total = detail ? detail.steps.length : 0;
  const percent = total > 0 ? Math.round((passed / total) * 100) : 0;

  // Tasks whose step was deleted afterwards are shown by their title.
  const orphanTasks: CaseTask[] = detail
    ? detail.tasks.filter(function (t) {
        return !detail.steps.some(function (s) {
          return s.id === t.workflow_step_id;
        });
      })
    : [];

  function taskLine(t: CaseTask) {
    if (!ctx) return null;
    return (
      <p className="mt-0.5 text-xs text-gray-400">
        {departmentName(ctx, t.department_id)} · {t.assigned_to_employee_id ? employeeName(ctx, t.assigned_to_employee_id) : "Unassigned, needs an owner"}
        {t.due_at ? " · Due " + formatDateTime(t.due_at) : ""} · Task {statusLabel(t.status).toLowerCase()}
        {t.status === "cancelled" && t.cancel_reason ? " · " + t.cancel_reason : ""}
      </p>
    );
  }

  return (
    <AppShell
      activeLabel="Workflow"
      title={detail ? detail.subject : "Workflow case"}
      breadcrumb="Dashboard > Workflow > Cases > Case"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/workflow/tracker" className="text-sm font-medium text-gray-400 hover:text-gray-200">
          Back to cases
        </Link>
      }
    >
      {ctxError ? <div className="mb-4 rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div> : null}
      {!caseId ? <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-sm text-gray-400">Choose a case from the list to see its progress.</div> : null}
      {loading || (caseId && !ctx && !ctxError) ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {!loading && result && result.error ? <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{result.error}</div> : null}

      {!loading && ctx && detail ? (
        <div className="max-w-4xl space-y-6">
          {actionError && !cancelling ? <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{actionError}</div> : null}

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold">{detail.subject}</h2>
                <p className="mt-1 text-sm text-gray-400">{result && result.templateName ? result.templateName : "Workflow"}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={"rounded px-2 py-0.5 text-xs font-medium " + caseStatusClasses(detail.status)}>{caseStatusLabel(detail.status)}</span>
                {canCancelCase(ctx, detail) && !cancelling ? (
                  <button
                    type="button"
                    onClick={function () {
                      setActionError("");
                      setCancelling(true);
                    }}
                    className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/10"
                  >
                    Cancel case
                  </button>
                ) : null}
              </div>
            </div>

            <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-gray-500">Started</dt>
                <dd className="mt-0.5 text-gray-200">{formatDateTime(detail.started_at)}</dd>
              </div>
              {detail.completed_at ? (
                <div>
                  <dt className="text-xs text-gray-500">Completed</dt>
                  <dd className="mt-0.5 text-gray-200">{formatDateTime(detail.completed_at)}</dd>
                </div>
              ) : null}
            </dl>

            {detail.status === "cancelled" ? (
              <div className="mt-5 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm">
                <p className="text-xs text-gray-500">Why it was cancelled</p>
                <p className="mt-1 whitespace-pre-wrap text-gray-200">{detail.cancel_reason || "No reason recorded."}</p>
              </div>
            ) : null}

            <div className="mt-6">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>
                  {passed} of {total} steps passed
                </span>
                <span>{percent}%</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-indigo-500" style={{ width: percent + "%" }} />
              </div>
            </div>
          </div>

          {cancelling ? (
            <div className="space-y-4 rounded-2xl border border-red-500/30 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold">Cancel this case?</h3>
              <p className="text-sm text-gray-400">
                The step that is open right now is cancelled with the same reason, and no later step is created. Steps already done stay done. This can&apos;t be undone.
              </p>
              {actionError ? <p className="text-sm text-red-300">{actionError}</p> : null}
              <div>
                <label className="mb-1 block text-xs text-gray-500">Reason (required)</label>
                <textarea
                  rows={3}
                  maxLength={500}
                  value={reason}
                  onChange={function (e) {
                    setReason(e.target.value);
                  }}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <button type="button" disabled={busy} onClick={confirmCancel} className="rounded-lg bg-red-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-60">
                  {busy ? "Cancelling…" : "Cancel case"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={function () {
                    setCancelling(false);
                    setActionError("");
                  }}
                  className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5"
                >
                  Keep case
                </button>
              </div>
            </div>
          ) : null}

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h3 className="text-base font-semibold">Progress</h3>
            <p className="mt-1 text-xs text-gray-500">The steps follow the template as it is now, so they can change while a case is running.</p>
            {detail.steps.length === 0 && orphanTasks.length === 0 ? <p className="mt-4 text-sm text-gray-500">This template has no steps.</p> : null}
            <ol className="mt-4 space-y-3">
              {detail.steps.map(function (step) {
                const task = taskForStep(step, detail.tasks);
                const state = stepState(task);
                return (
                  <li key={step.id} className="rounded-xl border border-white/10 bg-[#0a0e1a] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold">
                          <span className="mr-2 text-indigo-300">{step.step_order}.</span>
                          {step.name}
                        </p>
                        {task ? taskLine(task) : <p className="mt-0.5 text-xs text-gray-500">{departmentName(ctx, step.department_id)} · Not reached yet</p>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={"rounded px-2 py-0.5 text-xs font-medium " + stepStateClasses(state)}>{stepStateLabel(state)}</span>
                        {task ? (
                          <Link href={"/tasks/" + task.id} className="text-xs font-medium text-indigo-400 hover:text-indigo-300">
                            Open task
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </li>
                );
              })}
              {orphanTasks.map(function (t) {
                return (
                  <li key={t.id} className="rounded-xl border border-white/10 bg-[#0a0e1a] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold">{t.title}</p>
                        {taskLine(t)}
                        <p className="mt-0.5 text-xs text-gray-500">This step was removed from the template after the task was made.</p>
                      </div>
                      <Link href={"/tasks/" + t.id} className="text-xs font-medium text-indigo-400 hover:text-indigo-300">
                        Open task
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

export default function CaseDetailPage() {
  return (
    <Suspense fallback={null}>
      <CaseDetailContent />
    </Suspense>
  );
}
