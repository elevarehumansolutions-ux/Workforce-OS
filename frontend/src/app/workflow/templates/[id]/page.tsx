"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { activeEmployees, departmentName, employeeName, errorMessage, fullName, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext } from "@/lib/tasks";
import { canManageTemplates, canStartCase, turnaroundLabel } from "@/lib/workflow";
import type { WorkflowStep, WorkflowTemplate } from "@/lib/workflow";

interface TemplateResult {
  key: string;
  template: WorkflowTemplate | null;
  steps: WorkflowStep[];
  error: string;
}

type Panel = "none" | "rename" | "add" | "edit";

export default function WorkflowTemplateDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const templateId = params.id;

  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<TemplateResult | null>(null);
  const [panel, setPanel] = useState<Panel>("none");
  const [editingStepId, setEditingStepId] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [panelError, setPanelError] = useState("");

  // rename form
  const [nameDraft, setNameDraft] = useState("");
  const [templateDeptDraft, setTemplateDeptDraft] = useState("");

  // step form
  const [stepName, setStepName] = useState("");
  const [stepDept, setStepDept] = useState("");
  const [stepAssignee, setStepAssignee] = useState("");
  const [stepHours, setStepHours] = useState("");
  const [stepPosition, setStepPosition] = useState("");

  const key = [templateId, reloadCounter].join("|");
  const loading = result === null || result.key !== key;

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
      Promise.all([
        apiFetch<WorkflowTemplate>("/workflow-templates/" + templateId, { method: "GET" }),
        // The steps come back as a plain array in order, not paginated.
        apiFetch<WorkflowStep[]>("/workflow-templates/" + templateId + "/steps", { method: "GET" }),
      ])
        .then(function (res) {
          if (cancelled) return;
          setResult({ key: key, template: res[0], steps: Array.isArray(res[1]) ? res[1] : [], error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            template: null,
            steps: [],
            error:
              err instanceof ApiError && err.code === "WORKFLOW_TEMPLATE_NOT_FOUND"
                ? "This template wasn't found. It may have been deleted."
                : errorMessage(err, "Couldn't load this template. Check your connection and try again."),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [templateId, key]
  );

  const template = result ? result.template : null;
  const steps = result ? result.steps : [];
  const manage = ctx !== null && canManageTemplates(ctx);
  const archived = template !== null && template.archived_at !== null;

  function closePanel() {
    setPanel("none");
    setEditingStepId("");
    setPanelError("");
  }

  function openRename() {
    if (!template) return;
    setNameDraft(template.name);
    setTemplateDeptDraft(template.department_id);
    setPanelError("");
    setActionError("");
    setPanel("rename");
  }

  function openAdd() {
    setStepName("");
    setStepDept(template ? template.department_id : "");
    setStepAssignee("");
    setStepHours("");
    setStepPosition("");
    setPanelError("");
    setActionError("");
    setEditingStepId("");
    setPanel("add");
  }

  function openEdit(step: WorkflowStep) {
    setStepName(step.name);
    setStepDept(step.department_id);
    setStepAssignee(step.default_assignee_employee_id || "");
    setStepHours(step.default_turnaround_hours === null ? "" : String(step.default_turnaround_hours));
    setPanelError("");
    setActionError("");
    setEditingStepId(step.id);
    setPanel("edit");
  }

  // Whole number above zero, or empty for "no deadline".
  function parseHours(): { ok: boolean; value: number | null } {
    const trimmed = stepHours.trim();
    if (trimmed === "") return { ok: true, value: null };
    if (!/^[0-9]+$/.test(trimmed) || Number(trimmed) < 1) return { ok: false, value: null };
    return { ok: true, value: Number(trimmed) };
  }

  async function saveTemplateDetails() {
    if (!template) return;
    const body: Record<string, string> = {};
    if (nameDraft.trim() === "") {
      setPanelError("The template needs a name.");
      return;
    }
    if (nameDraft.trim() !== template.name) body.name = nameDraft.trim();
    if (templateDeptDraft && templateDeptDraft !== template.department_id) body.department_id = templateDeptDraft;
    if (Object.keys(body).length === 0) {
      closePanel();
      return;
    }
    setBusy(true);
    setPanelError("");
    try {
      await apiFetch("/workflow-templates/" + template.id, { method: "PATCH", body: body });
      closePanel();
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setPanelError(errorMessage(err, "Couldn't save your changes. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  async function saveStep() {
    if (!template) return;
    if (stepName.trim() === "") {
      setPanelError("Give the step a name.");
      return;
    }
    if (!stepDept) {
      setPanelError("Choose the department that does this step.");
      return;
    }
    const hours = parseHours();
    if (!hours.ok) {
      setPanelError("The turnaround must be a whole number of hours above zero, or left empty for no deadline.");
      return;
    }
    setBusy(true);
    setPanelError("");
    try {
      if (panel === "add") {
        const body: Record<string, unknown> = { name: stepName.trim(), department_id: stepDept };
        if (stepAssignee) body.default_assignee_employee_id = stepAssignee;
        if (hours.value !== null) body.default_turnaround_hours = hours.value;
        // No position = added at the end; a number inserts there and later steps move down.
        if (stepPosition) body.step_order = Number(stepPosition);
        await apiFetch("/workflow-templates/" + template.id + "/steps", { method: "POST", body: body });
      } else {
        const current = steps.find(function (s) {
          return s.id === editingStepId;
        });
        if (!current) {
          closePanel();
          return;
        }
        // Only what changed is sent. Null clears the assignee or the turnaround.
        const body: Record<string, unknown> = {};
        if (stepName.trim() !== current.name) body.name = stepName.trim();
        if (stepDept !== current.department_id) body.department_id = stepDept;
        if ((stepAssignee || null) !== current.default_assignee_employee_id) body.default_assignee_employee_id = stepAssignee || null;
        if (hours.value !== current.default_turnaround_hours) body.default_turnaround_hours = hours.value;
        if (Object.keys(body).length > 0) {
          await apiFetch("/workflow-steps/" + current.id, { method: "PATCH", body: body });
        }
      }
      closePanel();
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setPanelError(errorMessage(err, "Couldn't save this step. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  async function deleteStep(step: WorkflowStep) {
    if (!window.confirm('Delete the step "' + step.name + '"? The steps after it move up one place.')) return;
    setActionError("");
    setBusy(true);
    try {
      await apiFetch("/workflow-steps/" + step.id, { method: "DELETE" });
      // The later steps were renumbered, so the list is read again.
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setActionError(errorMessage(err, "Couldn't delete this step. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  async function moveStep(index: number, delta: number) {
    if (!template) return;
    const target = index + delta;
    if (target < 0 || target >= steps.length) return;
    const ids = steps.map(function (s) {
      return s.id;
    });
    const moved = ids[index];
    ids[index] = ids[target];
    ids[target] = moved;
    setActionError("");
    setBusy(true);
    try {
      await apiFetch("/workflow-templates/" + template.id + "/steps/order", { method: "PUT", body: { step_ids: ids } });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      // 409 while cases are running on this template: the message explains.
      setActionError(errorMessage(err, "Couldn't change the order. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  async function toggleArchive() {
    if (!template) return;
    setActionError("");
    setBusy(true);
    try {
      await apiFetch("/workflow-templates/" + template.id + (archived ? "/unarchive" : "/archive"), { method: "POST" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      if (err instanceof ApiError && (err.code === "WORKFLOW_TEMPLATE_ALREADY_ARCHIVED" || err.code === "WORKFLOW_TEMPLATE_NOT_ARCHIVED")) {
        setReloadCounter(reloadCounter + 1);
      } else {
        setActionError(errorMessage(err, "Couldn't change this template. Check your connection and try again."));
      }
    } finally {
      setBusy(false);
    }
  }

  async function deleteTemplate() {
    if (!template) return;
    if (!window.confirm('Delete the template "' + template.name + '" and all its steps? This can\'t be undone.')) return;
    setActionError("");
    setBusy(true);
    try {
      await apiFetch("/workflow-templates/" + template.id, { method: "DELETE" });
      router.push("/workflow/templates");
    } catch (err) {
      setActionError(
        errorMessage(err, "Couldn't delete this template. Check your connection and try again.") +
          (err instanceof ApiError && err.code === "RESOURCE_IN_USE" ? " You can use Archive instead." : "")
      );
      setBusy(false);
    }
  }

  const inputClass = "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500";
  const smallButton = "rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40";

  const stepForm = (
    <div className="space-y-4 rounded-2xl border border-indigo-500/30 bg-[#0d1220]/80 p-6">
      <h3 className="text-base font-semibold">{panel === "add" ? "Add a step" : "Edit step"}</h3>
      {panelError ? <p className="text-sm text-red-300">{panelError}</p> : null}
      <div>
        <label className="mb-1 block text-xs text-gray-500">Step name</label>
        <input type="text" maxLength={200} value={stepName} onChange={function (e) { setStepName(e.target.value); }} placeholder="e.g. Finance review" className={inputClass} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs text-gray-500">Done by (department)</label>
          <select value={stepDept} onChange={function (e) { setStepDept(e.target.value); }} className={inputClass}>
            <option value="">Choose a department</option>
            {ctx
              ? ctx.departments.map(function (d) {
                  return (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  );
                })
              : null}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">Default person (optional)</label>
          <select value={stepAssignee} onChange={function (e) { setStepAssignee(e.target.value); }} className={inputClass}>
            <option value="">No one. The task lands with the department</option>
            {ctx
              ? activeEmployees(ctx).map(function (emp) {
                  return (
                    <option key={emp.id} value={emp.id}>
                      {fullName(emp)}
                    </option>
                  );
                })
              : null}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-500">Turnaround in hours (optional)</label>
          <input type="number" min={1} step={1} value={stepHours} onChange={function (e) { setStepHours(e.target.value); }} placeholder="No deadline" className={inputClass} />
          <p className="mt-1 text-xs text-gray-500">Counted in business hours: Monday to Friday, 9am to 5pm.</p>
        </div>
        {panel === "add" ? (
          <div>
            <label className="mb-1 block text-xs text-gray-500">Position</label>
            <select value={stepPosition} onChange={function (e) { setStepPosition(e.target.value); }} className={inputClass}>
              <option value="">At the end</option>
              {steps.map(function (s, index) {
                return (
                  <option key={s.id} value={String(index + 1)}>
                    {"Step " + (index + 1) + " (the current step " + (index + 1) + " moves down)"}
                  </option>
                );
              })}
            </select>
          </div>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <button type="button" disabled={busy} onClick={saveStep} className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60">
          {busy ? "Saving…" : panel === "add" ? "Add step" : "Save step"}
        </button>
        <button type="button" disabled={busy} onClick={closePanel} className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5">
          Cancel
        </button>
      </div>
    </div>
  );

  return (
    <AppShell
      activeLabel="Workflow"
      title={template ? template.name : "Workflow template"}
      breadcrumb="Dashboard > Workflow > Templates > Template"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/workflow/templates" className="text-sm font-medium text-gray-400 hover:text-gray-200">
          Back to templates
        </Link>
      }
    >
      {ctxError ? <div className="mb-4 rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div> : null}
      {loading || !ctx ? (!ctxError ? <p className="text-sm text-gray-400">Loading…</p> : null) : null}
      {!loading && result && result.error ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{result.error}</div>
      ) : null}

      {!loading && ctx && template ? (
        <div className="max-w-4xl space-y-6">
          {actionError ? <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{actionError}</div> : null}

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold">
                  {template.name}
                  {archived ? <span className="ml-3 rounded bg-gray-500/20 px-2 py-0.5 align-middle text-xs font-medium text-gray-400">Archived</span> : null}
                </h2>
                <p className="mt-1 text-sm text-gray-400">Owned by {departmentName(ctx, template.department_id)}</p>
                {archived ? <p className="mt-1 text-xs text-gray-500">Archived templates can&apos;t start new cases. Cases already running carry on.</p> : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {!archived && canStartCase(ctx) ? (
                  steps.length > 0 ? (
                    <Link href={"/workflow/start?template=" + template.id} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
                      Start a case
                    </Link>
                  ) : (
                    <span className="text-xs text-gray-500">Add a step to start a case</span>
                  )
                ) : null}
                {manage ? (
                  <>
                    <button type="button" disabled={busy} onClick={openRename} className={smallButton}>
                      Rename / change department
                    </button>
                    <button type="button" disabled={busy} onClick={toggleArchive} className={smallButton}>
                      {archived ? "Unarchive" : "Archive"}
                    </button>
                    <button type="button" disabled={busy} onClick={deleteTemplate} className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/10 disabled:opacity-40">
                      Delete
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          </div>

          {panel === "rename" ? (
            <div className="space-y-4 rounded-2xl border border-indigo-500/30 bg-[#0d1220]/80 p-6">
              <h3 className="text-base font-semibold">Rename or change department</h3>
              {panelError ? <p className="text-sm text-red-300">{panelError}</p> : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Template name</label>
                  <input type="text" maxLength={200} value={nameDraft} onChange={function (e) { setNameDraft(e.target.value); }} className={inputClass} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Owning department</label>
                  <select value={templateDeptDraft} onChange={function (e) { setTemplateDeptDraft(e.target.value); }} className={inputClass}>
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
              <div className="flex items-center gap-2">
                <button type="button" disabled={busy} onClick={saveTemplateDetails} className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-60">
                  {busy ? "Saving…" : "Save"}
                </button>
                <button type="button" disabled={busy} onClick={closePanel} className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5">
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold">Steps</h3>
              {manage && panel === "none" ? (
                <button type="button" disabled={busy} onClick={openAdd} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-60">
                  + Add step
                </button>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              When a case runs, each step becomes a task for its department once the step before it ends. Steps can&apos;t be reordered or deleted (if they have open tasks) while cases are running on this template.
            </p>

            {steps.length === 0 ? (
              <p className="mt-6 rounded-lg border border-dashed border-white/15 px-4 py-8 text-center text-sm text-gray-500">
                This template has no steps yet.{manage ? " Add the first step to get started." : ""}
              </p>
            ) : (
              <ol className="mt-4 space-y-3">
                {steps.map(function (step, index) {
                  return (
                    <li key={step.id} className="rounded-xl border border-white/10 bg-[#0a0e1a] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex gap-3">
                          <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                            {step.step_order}
                          </span>
                          <div>
                            <p className="text-sm font-semibold">{step.name}</p>
                            <p className="mt-0.5 text-xs text-gray-400">
                              {departmentName(ctx, step.department_id)} ·{" "}
                              {step.default_assignee_employee_id ? employeeName(ctx, step.default_assignee_employee_id) : "Lands with the department"} ·{" "}
                              {turnaroundLabel(step.default_turnaround_hours)}
                            </p>
                          </div>
                        </div>
                        {manage ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <button type="button" disabled={busy || index === 0} onClick={function () { moveStep(index, -1); }} className={smallButton} aria-label="Move step up">
                              Up
                            </button>
                            <button type="button" disabled={busy || index === steps.length - 1} onClick={function () { moveStep(index, 1); }} className={smallButton} aria-label="Move step down">
                              Down
                            </button>
                            <button type="button" disabled={busy} onClick={function () { openEdit(step); }} className={smallButton}>
                              Edit
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={function () {
                                deleteStep(step);
                              }}
                              className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/10 disabled:opacity-40"
                            >
                              Delete
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>

          {panel === "add" || panel === "edit" ? stepForm : null}
        </div>
      ) : null}
    </AppShell>
  );
}
