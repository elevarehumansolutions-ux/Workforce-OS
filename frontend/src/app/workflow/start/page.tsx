"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { departmentName, errorMessage, fetchAllPages, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext } from "@/lib/tasks";
import { canManageTemplates, canStartCase, turnaroundLabel } from "@/lib/workflow";
import type { WorkflowCase, WorkflowStep, WorkflowTemplate } from "@/lib/workflow";

interface TemplatesResult {
  key: string;
  templates: WorkflowTemplate[];
  error: string;
}

interface StepsResult {
  key: string;
  steps: WorkflowStep[];
  error: string;
}

function StartWorkflowContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const presetTemplate = searchParams.get("template") || "";

  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [reloadCounter, setReloadCounter] = useState(0);
  const [templatesResult, setTemplatesResult] = useState<TemplatesResult | null>(null);
  const [chosenId, setChosenId] = useState(presetTemplate);
  const [subject, setSubject] = useState("");
  // What the job is worth (naira) and the client's final deadline; both optional.
  const [jobValue, setJobValue] = useState("");
  const [deadline, setDeadline] = useState("");
  // Set when a figure was entered without a deadline: the person must confirm or add one.
  const [askAboutDeadline, setAskAboutDeadline] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [stepsResult, setStepsResult] = useState<StepsResult | null>(null);

  const templatesKey = "templates|" + reloadCounter;
  const templatesLoading = templatesResult === null || templatesResult.key !== templatesKey;
  const templates = templatesResult ? templatesResult.templates : [];

  // The picker only offers templates that are still in the list (archived ones are hidden by default).
  const selectedId = templates.some(function (t) {
    return t.id === chosenId;
  })
    ? chosenId
    : templates.length > 0
      ? templates[0].id
      : "";
  const selected = templates.find(function (t) {
    return t.id === selectedId;
  });

  const stepsKey = "steps|" + selectedId + "|" + reloadCounter;
  const stepsLoading = selectedId !== "" && (stepsResult === null || stepsResult.key !== stepsKey);
  const steps = stepsResult && stepsResult.key === stepsKey ? stepsResult.steps : [];
  const stepsError = stepsResult && stepsResult.key === stepsKey ? stepsResult.error : "";

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
      let cancelled = false;
      fetchAllPages<WorkflowTemplate>("/workflow-templates")
        .then(function (list) {
          if (cancelled) return;
          setTemplatesResult({ key: templatesKey, templates: list, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setTemplatesResult({ key: templatesKey, templates: [], error: errorMessage(err, "Couldn't load the templates. Check your connection and try again.") });
        });
      return function () {
        cancelled = true;
      };
    },
    [templatesKey]
  );

  useEffect(
    function () {
      if (!selectedId) return;
      let cancelled = false;
      apiFetch<WorkflowStep[]>("/workflow-templates/" + selectedId + "/steps", { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setStepsResult({ key: stepsKey, steps: Array.isArray(res) ? res : [], error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setStepsResult({ key: stepsKey, steps: [], error: errorMessage(err, "Couldn't load this template's steps.") });
        });
      return function () {
        cancelled = true;
      };
    },
    [selectedId, stepsKey]
  );

  async function start(skipDeadlineWarning: boolean) {
    setError("");
    if (!selectedId) {
      setError("Choose a template.");
      return;
    }
    if (!subject.trim()) {
      setError("Enter who or what this case is for, e.g. a client name.");
      return;
    }
    // The figure, as a number: "2,000,000" and "2000000" are both fine.
    const cleaned = jobValue.replace(/[,\s₦]/g, "");
    const figure = cleaned === "" ? null : Number(cleaned);
    if (figure !== null && (Number.isNaN(figure) || figure < 0)) {
      setError("Enter the figure as a number of naira, for example 2000000.");
      return;
    }
    // A deadline is entered as a date; the client expects it done by the end of that day.
    let deadlineIso: string | null = null;
    if (deadline !== "") {
      const end = new Date(deadline + "T23:59:00");
      if (end.getTime() <= Date.now()) {
        setError("The client's final deadline must be a date in the future.");
        return;
      }
      deadlineIso = end.toISOString();
    }
    // A figure with no deadline can be at risk but can never be counted as lost by time,
    // so tell the person first and let them add a deadline or carry on without one.
    if (figure !== null && figure > 0 && deadlineIso === null && !skipDeadlineWarning) {
      setAskAboutDeadline(true);
      return;
    }
    setAskAboutDeadline(false);
    setStarting(true);
    try {
      const created = await apiFetch<WorkflowCase>("/workflow-instances", {
        method: "POST",
        body: {
          template_id: selectedId,
          subject: subject.trim(),
          client_value: figure,
          client_deadline_at: deadlineIso,
        },
      });
      router.push("/workflow/case-detail?id=" + created.id);
    } catch (err) {
      setError(errorMessage(err, "Couldn't start the workflow. Check your connection and try again."));
      // The template was deleted or archived after the picker loaded: refresh it.
      if (err instanceof ApiError && (err.code === "WORKFLOW_TEMPLATE_NOT_FOUND" || err.code === "WORKFLOW_TEMPLATE_ARCHIVED")) {
        setReloadCounter(reloadCounter + 1);
      }
      setStarting(false);
    }
  }

  const inputClass = "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500";
  const noSteps = selectedId !== "" && !stepsLoading && !stepsError && steps.length === 0;

  return (
    <AppShell
      activeLabel="Workflow"
      title="Start workflow"
      breadcrumb="Dashboard > Workflow > Start"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/workflow/templates" className="text-sm font-medium text-gray-400 hover:text-gray-200">
          Back to templates
        </Link>
      }
    >
      {ctxError ? <div className="mb-4 rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div> : null}
      {!ctx && !ctxError ? <p className="text-sm text-gray-400">Loading…</p> : null}

      {ctx && !canStartCase(ctx) ? (
        <div className="max-w-xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-sm text-gray-400">
          Only employees and HR administrators can start a workflow.
        </div>
      ) : null}

      {ctx && canStartCase(ctx) ? (
        <div className="max-w-2xl space-y-5 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6">
          {error ? <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div> : null}
          {templatesResult && templatesResult.error ? <p className="text-sm text-red-300">{templatesResult.error}</p> : null}
          {templatesLoading ? <p className="text-sm text-gray-400">Loading templates…</p> : null}

          {!templatesLoading && templates.length === 0 && !(templatesResult && templatesResult.error) ? (
            <div className="space-y-3">
              <p className="text-sm text-gray-400">
                There are no workflow templates to start yet. A template is the list of steps a case goes through,
                and it has to exist before a case can be started.
              </p>
              {canManageTemplates(ctx) ? (
                <Link
                  href="/workflow/new-template"
                  className="inline-block rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600"
                >
                  Create a template
                </Link>
              ) : (
                <p className="text-sm text-gray-500">Ask an HR administrator or a manager to create one.</p>
              )}
            </div>
          ) : null}

          {!templatesLoading && templates.length > 0 ? (
            <>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-200">Template</label>
                <select
                  value={selectedId}
                  onChange={function (e) {
                    setChosenId(e.target.value);
                    setError("");
                  }}
                  className={inputClass}
                >
                  {templates.map(function (t) {
                    return (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    );
                  })}
                </select>
                {selected ? <p className="mt-1 text-xs text-gray-500">Owned by {departmentName(ctx, selected.department_id)}</p> : null}
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-gray-200">Who or what is this case for?</label>
                <input
                  type="text"
                  maxLength={200}
                  value={subject}
                  onChange={function (e) {
                    setSubject(e.target.value);
                  }}
                  placeholder="e.g. Zenith Ltd"
                  className={inputClass}
                />
              </div>

              <div className="rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">What this job is worth (optional)</p>
                <p className="mt-1 text-xs text-gray-500">
                  For example the fee a client pays you for this job. Every task in the case shares it. While a task runs
                  late, the figure shows as at risk; if the job is cancelled or the deadline is missed, it counts as lost.
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-300">Amount (₦)</label>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={jobValue}
                      onChange={function (e) {
                        setJobValue(e.target.value);
                        setAskAboutDeadline(false);
                      }}
                      placeholder="e.g. 2,000,000"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-300">Client&apos;s final deadline</label>
                    <input
                      type="date"
                      value={deadline}
                      onChange={function (e) {
                        setDeadline(e.target.value);
                        setAskAboutDeadline(false);
                      }}
                      className={inputClass + " [color-scheme:dark]"}
                    />
                  </div>
                </div>

                {askAboutDeadline ? (
                  <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                    <p className="text-sm font-medium text-amber-200">No final deadline was entered.</p>
                    <p className="mt-1 text-xs text-amber-200/80">
                      Without a deadline this figure can show as at risk, but it can only be counted as lost if you
                      cancel the case. Add the date the client expects the job done, or save without one.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={function () { setAskAboutDeadline(false); }}
                        className="rounded-lg bg-amber-500 px-4 py-2 text-xs font-semibold text-black hover:bg-amber-400"
                      >
                        Add a deadline
                      </button>
                      <button
                        type="button"
                        onClick={function () { start(true); }}
                        className="rounded-lg border border-white/20 px-4 py-2 text-xs font-medium text-gray-200 hover:bg-white/5"
                      >
                        Save without a deadline
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">What will happen</p>
                {stepsLoading ? <p className="mt-2 text-sm text-gray-400">Loading steps…</p> : null}
                {stepsError ? <p className="mt-2 text-sm text-red-300">{stepsError}</p> : null}
                {noSteps ? (
                  <p className="mt-2 text-sm text-amber-300">This template has no steps yet. Add at least one step before starting a case.</p>
                ) : null}
                {steps.length > 0 ? (
                  <>
                    <p className="mt-2 text-xs text-gray-500">The first step&apos;s task is created straight away. Each later step&apos;s task is created when the step before it ends.</p>
                    <ol className="mt-3 space-y-2">
                      {steps.map(function (s) {
                        return (
                          <li key={s.id} className="text-sm text-gray-300">
                            <span className="mr-2 text-indigo-300">{s.step_order}.</span>
                            {s.name}
                            <span className="text-xs text-gray-500">
                              {" "}
                              · {departmentName(ctx, s.department_id)} · {turnaroundLabel(s.default_turnaround_hours)}
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                  </>
                ) : null}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={starting || stepsLoading || noSteps || !!stepsError}
                  onClick={function () { start(false); }}
                  className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {starting ? "Starting…" : "Start workflow"}
                </button>
                <Link href="/workflow/templates" className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5">
                  Cancel
                </Link>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </AppShell>
  );
}

export default function StartWorkflowPage() {
  return (
    <Suspense fallback={null}>
      <StartWorkflowContent />
    </Suspense>
  );
}
