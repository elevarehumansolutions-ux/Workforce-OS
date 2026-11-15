"use client";

import { Fragment, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PersonSelect from "@/components/PersonSelect";
import { currentPersonOption, departmentName, employeeName, errorMessage, loadCaller, peopleOfDepartment, roleLabel } from "@/lib/tasks";
import { closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import { arrayMove, SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";
import Modal from "@/components/Modal";
import SortableStepRow from "@/components/SortableStepRow";
import type { CallerContext } from "@/lib/tasks";
import { canManageTemplates, canStartCase, turnaroundLabel, whoReceivesTask } from "@/lib/workflow";
import type { CompletionRule, ParticipantDraft, WorkflowStep, WorkflowTemplate } from "@/lib/workflow";
import { describeWorkingHours, fetchWorkingHours } from "@/lib/workingHours";
import type { WorkingHours } from "@/lib/workingHours";

interface TemplateResult {
  key: string;
  template: WorkflowTemplate | null;
  steps: WorkflowStep[];
  error: string;
}

type Panel = "none" | "rename" | "add" | "edit";

// A KPI's name for the step list; the list of KPIs comes with the caller's context.
function kpiNameOf(ctx: CallerContext, kpiId: string): string {
  for (const k of ctx.kpis) {
    if (k.id === kpiId) return k.name;
  }
  return "linked";
}

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
  // The turnaround number, and whether it counts hours or working days.
  const [stepHours, setStepHours] = useState("");
  const [stepUnit, setStepUnit] = useState<"hours" | "days">("hours");
  // The company's working week, only to explain what "1 day" means under the field.
  const [week, setWeek] = useState<WorkingHours | null>(null);
  const [stepPosition, setStepPosition] = useState("");
  // The KPI the step's tasks count toward ("" = none). It must be a KPI of the step's department.
  const [stepKpi, setStepKpi] = useState("");
  // Other departments that do this step together with the one above, and when the case moves on.
  const [stepParticipants, setStepParticipants] = useState<ParticipantDraft[]>([]);
  const [stepRule, setStepRule] = useState<CompletionRule>("all");

  // A drag starts only after the pointer has moved a few pixels, so a plain click on the handle is not a drag.
  // The keyboard works too: focus the handle, press Space, use the arrow keys, press Space again.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

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
    // Only used to explain what "1 day" means; if it fails the hint just stays general.
    fetchWorkingHours()
      .then(function (loaded) {
        if (!cancelled) setWeek(loaded);
      })
      .catch(function () {});
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

  // `position` is the place the new step should take (1 = first); without it the step goes at the end.
  function openAdd(position?: number) {
    setStepName("");
    setStepDept(template ? template.department_id : "");
    setStepAssignee("");
    setStepHours("");
    setStepUnit("hours");
    setStepPosition(position ? String(position) : "");
    setStepKpi("");
    setStepParticipants([]);
    setStepRule("all");
    setPanelError("");
    setActionError("");
    setEditingStepId("");
    setPanel("add");
  }

  function openEdit(step: WorkflowStep) {
    setStepName(step.name);
    setStepDept(step.department_id);
    setStepAssignee(step.default_assignee_employee_id || "");
    setStepKpi(step.kpi_id || "");
    setStepParticipants(
      step.participants.map(function (p) {
        return {
          department_id: p.department_id,
          default_assignee_employee_id: p.default_assignee_employee_id || "",
          kpi_id: p.kpi_id || "",
        };
      })
    );
    setStepRule(step.completion_rule);
    // A step given in days shows its number of days; otherwise its hours (or empty for no deadline).
    if (step.default_turnaround_days !== null) {
      setStepHours(String(step.default_turnaround_days));
      setStepUnit("days");
    } else {
      setStepHours(step.default_turnaround_hours === null ? "" : String(step.default_turnaround_hours));
      setStepUnit("hours");
    }
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

  function addParticipant() {
    setStepParticipants(stepParticipants.concat([{ department_id: "", default_assignee_employee_id: "", kpi_id: "" }]));
  }

  // Changes some fields of one extra department (the others stay as they are).
  function updateParticipant(index: number, change: Partial<ParticipantDraft>) {
    setStepParticipants(
      stepParticipants.map(function (p, i) {
        return i === index ? { ...p, ...change } : p;
      })
    );
  }

  function removeParticipant(index: number) {
    setStepParticipants(
      stepParticipants.filter(function (_p, i) {
        return i !== index;
      })
    );
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
      setPanelError("The turnaround must be a whole number above zero, or left empty for no deadline.");
      return;
    }
    for (const p of stepParticipants) {
      if (!p.department_id) {
        setPanelError("Choose a department for each extra department, or remove the empty one.");
        return;
      }
    }
    // The extra departments as the server wants them (empty text becomes null).
    const participantsPayload = stepParticipants.map(function (p) {
      return {
        department_id: p.department_id,
        default_assignee_employee_id: p.default_assignee_employee_id || null,
        kpi_id: p.kpi_id || null,
      };
    });
    setBusy(true);
    setPanelError("");
    try {
      if (panel === "add") {
        const body: Record<string, unknown> = { name: stepName.trim(), department_id: stepDept };
        if (stepAssignee) body.default_assignee_employee_id = stepAssignee;
        if (stepKpi) body.kpi_id = stepKpi;
        if (participantsPayload.length > 0) {
          body.participants = participantsPayload;
          body.completion_rule = stepRule;
        }
        if (hours.value !== null && stepUnit === "days") body.default_turnaround_days = hours.value;
        if (hours.value !== null && stepUnit === "hours") body.default_turnaround_hours = hours.value;
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
        if ((stepKpi || null) !== current.kpi_id) body.kpi_id = stepKpi || null;
        // The extra departments are sent as a whole list (it replaces the old one) and only when changed.
        const oldParticipants = JSON.stringify(
          current.participants.map(function (p) {
            return { department_id: p.department_id, default_assignee_employee_id: p.default_assignee_employee_id, kpi_id: p.kpi_id };
          })
        );
        if (JSON.stringify(participantsPayload) !== oldParticipants) body.participants = participantsPayload;
        if (participantsPayload.length > 0 && stepRule !== current.completion_rule) body.completion_rule = stepRule;
        // The turnaround counts as changed when the number OR the unit differs. Sending the new unit makes the
        // server clear the old one; "no deadline" clears both.
        const newHours = stepUnit === "hours" ? hours.value : null;
        const newDays = stepUnit === "days" ? hours.value : null;
        if (newHours !== current.default_turnaround_hours || newDays !== current.default_turnaround_days) {
          if (hours.value === null) {
            body.default_turnaround_hours = null;
            body.default_turnaround_days = null;
          } else if (stepUnit === "days") {
            body.default_turnaround_days = hours.value;
          } else {
            body.default_turnaround_hours = hours.value;
          }
        }
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

  // Saves a new order (the list of step ids, first to last). Used by the Up/Down buttons and by a drop.
  async function saveOrder(ids: string[]) {
    if (!template) return;
    setActionError("");
    setBusy(true);
    try {
      await apiFetch("/workflow-templates/" + template.id + "/steps/order", { method: "PUT", body: { step_ids: ids } });
    } catch (err) {
      // 409 while cases are running on this template: the message explains.
      setActionError(errorMessage(err, "Couldn't change the order. Check your connection and try again."));
    } finally {
      setBusy(false);
      // Read the list again either way: after a failure this puts a dropped step back where it really is.
      setReloadCounter(reloadCounter + 1);
    }
  }

  function moveStep(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= steps.length) return;
    const ids = steps.map(function (s) {
      return s.id;
    });
    const moved = ids[index];
    ids[index] = ids[target];
    ids[target] = moved;
    saveOrder(ids);
  }

  // A step was dropped on another one: it takes that one's place.
  function onDragEnd(event: DragEndEvent) {
    if (!event.over || event.active.id === event.over.id) return;
    const ids = steps.map(function (s) {
      return s.id;
    });
    const from = ids.indexOf(String(event.active.id));
    const to = ids.indexOf(String(event.over.id));
    if (from === -1 || to === -1) return;
    const newIds = arrayMove(ids, from, to);
    // Show the new order at once, so the step does not jump back while the server is answering.
    if (result) {
      const byId: Record<string, WorkflowStep> = {};
      steps.forEach(function (s) {
        byId[s.id] = s;
      });
      setResult({ ...result, steps: newIds.map(function (id) { return byId[id]; }) });
    }
    saveOrder(newIds);
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

  // The window title says where the new step will land, so no position field is needed.
  const placeNumber = Number(stepPosition);
  const placeStep = placeNumber >= 1 ? steps[placeNumber - 1] : undefined;
  const addTitle = placeStep
    ? "Add a step before step " + placeNumber + " (" + placeStep.name + ")"
    : steps.length === 0
      ? "Add the first step"
      : "Add a step at the end (after step " + steps.length + ")";

  const inputClass ="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500";
  const smallButton = "rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40";

  const stepForm = (
    <div className="space-y-4">
      {panelError ? <p className="text-sm text-red-300">{panelError}</p> : null}
      <div>
        <label className="mb-1 block text-xs text-gray-500">Step name</label>
        <input type="text" maxLength={200} value={stepName} onChange={function (e) { setStepName(e.target.value); }} placeholder="e.g. Finance review" className={inputClass} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs text-gray-500">Done by (department)</label>
          <select
            value={stepDept}
            onChange={function (e) {
              setStepDept(e.target.value);
              // A KPI and a person belong to one department, so both choices are cleared when it changes.
              setStepKpi("");
              setStepAssignee("");
            }}
            className={inputClass}
          >
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
          {ctx ? (
            <PersonSelect
              people={peopleOfDepartment(ctx, stepDept)}
              positions={ctx.positions}
              departments={ctx.departments}
              value={stepAssignee}
              onChange={setStepAssignee}
              emptyLabel={stepDept ? "No one named" : "Choose the department first"}
              extraOption={currentPersonOption(ctx, stepAssignee, peopleOfDepartment(ctx, stepDept))}
              disabled={!stepDept}
              className={inputClass}
            />
          ) : null}
          {ctx && !stepAssignee && stepDept ? (
            <p className="mt-1 text-xs text-gray-500">{whoReceivesTask(ctx, stepDept, false)}</p>
          ) : null}
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1 block text-xs text-gray-500">Counts toward KPI (optional)</label>
          <select
            value={stepKpi}
            disabled={!stepDept}
            onChange={function (e) { setStepKpi(e.target.value); }}
            className={inputClass + " max-w-md"}
          >
            <option value="">{stepDept ? "Not linked: its tasks won't count in performance scores" : "Choose the department first"}</option>
            {ctx
              ? ctx.kpis
                  .filter(function (k) { return k.department_id === stepDept; })
                  .map(function (k) {
                    return (
                      <option key={k.id} value={k.id}>
                        {k.name}
                      </option>
                    );
                  })
              : null}
          </select>
          <p className="mt-1 text-xs text-gray-500">
            Pick the KPI of this department that the work counts toward, so each finished task shows up in its score.
            {ctx && stepDept && ctx.kpis.filter(function (k) { return k.department_id === stepDept; }).length === 0
              ? " This department has no KPIs yet."
              : ""}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 p-4 sm:col-span-2">
          <p className="text-sm font-medium text-gray-200">Done together with other departments (optional)</p>
          <p className="mt-1 text-xs text-gray-500">
            Add a department when it must do part of this step too. Each one gets a task of its own, and its head or
            named person is told and emailed.
          </p>
          {stepParticipants.map(function (p, index) {
            return (
              <div key={index} className="mt-3 grid gap-3 border-t border-white/10 pt-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Department</label>
                  <select
                    value={p.department_id}
                    onChange={function (e) { updateParticipant(index, { department_id: e.target.value, kpi_id: "", default_assignee_employee_id: "" }); }}
                    className={inputClass}
                  >
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
                  <label className="mb-1 block text-xs text-gray-500">Person (optional)</label>
                  {ctx ? (
                    <PersonSelect
                      people={peopleOfDepartment(ctx, p.department_id)}
                      positions={ctx.positions}
                      departments={ctx.departments}
                      value={p.default_assignee_employee_id}
                      onChange={function (id) { updateParticipant(index, { default_assignee_employee_id: id }); }}
                      emptyLabel={p.department_id ? "No one named" : "Choose the department first"}
                      extraOption={currentPersonOption(ctx, p.default_assignee_employee_id, peopleOfDepartment(ctx, p.department_id))}
                      disabled={!p.department_id}
                      className={inputClass}
                    />
                  ) : null}
                  {ctx && p.department_id && !p.default_assignee_employee_id ? (
                    <p className="mt-1 text-xs text-gray-500">{whoReceivesTask(ctx, p.department_id, false)}</p>
                  ) : null}
                </div>
                <div>
                  <label className="mb-1 block text-xs text-gray-500">Counts toward KPI (optional)</label>
                  <select
                    value={p.kpi_id}
                    disabled={!p.department_id}
                    onChange={function (e) { updateParticipant(index, { kpi_id: e.target.value }); }}
                    className={inputClass}
                  >
                    <option value="">{p.department_id ? "Not linked: won't count in scores" : "Choose the department first"}</option>
                    {ctx
                      ? ctx.kpis
                          .filter(function (k) { return k.department_id === p.department_id; })
                          .map(function (k) {
                            return (
                              <option key={k.id} value={k.id}>
                                {k.name}
                              </option>
                            );
                          })
                      : null}
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    type="button"
                    onClick={function () { removeParticipant(index); }}
                    className="rounded-lg border border-red-500/40 px-3 py-2 text-xs font-medium text-red-300 hover:bg-red-500/10"
                  >
                    Remove this department
                  </button>
                </div>
              </div>
            );
          })}
          <button
            type="button"
            disabled={stepParticipants.length >= 5}
            onClick={addParticipant}
            className="mt-3 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
          >
            + Add a department
          </button>
          {stepParticipants.length > 0 ? (
            <fieldset className="mt-4 space-y-2 border-t border-white/10 pt-3">
              <legend className="text-xs text-gray-500">When does the case move on?</legend>
              <label className="flex items-start gap-2 text-sm text-gray-300">
                <input type="radio" name="completion-rule" checked={stepRule === "all"} onChange={function () { setStepRule("all"); }} className="mt-1" />
                <span>When every department has finished its part</span>
              </label>
              <label className="flex items-start gap-2 text-sm text-gray-300">
                <input type="radio" name="completion-rule" checked={stepRule === "lead"} onChange={function () { setStepRule("lead"); }} className="mt-1" />
                <span>When the department chosen under &quot;Done by&quot; finishes. The others only help, and their open tasks are closed.</span>
              </label>
            </fieldset>
          ) : null}
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1 block text-xs text-gray-500">Turnaround (optional)</label>
          <div className="flex max-w-md gap-2">
            <input type="number" min={1} step={1} value={stepHours} onChange={function (e) { setStepHours(e.target.value); }} placeholder="No deadline" className={inputClass + " min-w-[9rem] flex-1"} />
            <select
              value={stepUnit}
              onChange={function (e) { setStepUnit(e.target.value === "days" ? "days" : "hours"); }}
              className="w-28 shrink-0 rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
              aria-label="Turnaround unit"
            >
              <option value="hours">Hours</option>
              <option value="days">Days</option>
            </select>
          </div>
        </div>
      </div>
      <p className="text-xs text-gray-500">
        {week
          ? "Turnaround is counted in your working hours (" + describeWorkingHours(week) + "). One day is a full working day, " + week.hours_per_day + " hours. HR can change this in Settings."
          : "Turnaround is counted in your company's working hours. One day is a full working day."}
      </p>
      <div className="flex items-center justify-end gap-2 border-t border-white/10 pt-4">
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
                <button type="button" disabled={busy} onClick={function () { openAdd(); }} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-60">
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
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
              <SortableContext
                items={steps.map(function (s) { return s.id; })}
                strategy={verticalListSortingStrategy}
              >
              <ol className="mt-4">
                {steps.map(function (step, index) {
                  return (
                    <Fragment key={step.id}>
                      {manage && panel === "none" ? (
                        <li className="flex justify-center py-1">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={function () { openAdd(index + 1); }}
                            className="rounded-full px-3 py-0.5 text-xs text-gray-500 hover:bg-indigo-500/10 hover:text-indigo-300 disabled:opacity-40"
                          >
                            {index === 0 ? "+ Add a step before this one" : "+ Add a step here"}
                          </button>
                        </li>
                      ) : null}
                    <SortableStepRow id={step.id} canDrag={manage && !busy}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex gap-3">
                          <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                            {index + 1}
                          </span>
                          <div>
                            <p className="text-sm font-semibold">{step.name}</p>
                            <p className="mt-0.5 text-xs text-gray-400">
                              {departmentName(ctx, step.department_id)} ·{" "}
                              {step.default_assignee_employee_id ? employeeName(ctx, step.default_assignee_employee_id) : whoReceivesTask(ctx, step.department_id, true)} ·{" "}
                              {turnaroundLabel(step.default_turnaround_hours, step.default_turnaround_days)} ·{" "}
                              {step.kpi_id ? "KPI: " + kpiNameOf(ctx, step.kpi_id) : "No KPI"}
                            </p>
                            {step.participants.length > 0 ? (
                              <p className="mt-0.5 text-xs text-indigo-300">
                                Together with{" "}
                                {step.participants
                                  .map(function (p) {
                                    return departmentName(ctx, p.department_id) + (p.default_assignee_employee_id ? " (" + employeeName(ctx, p.default_assignee_employee_id) + ")" : "");
                                  })
                                  .join(", ")}
                                {step.completion_rule === "lead" ? ". The lead department decides; the others help." : ". The case moves on when every department has finished."}
                              </p>
                            ) : null}
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
                    </SortableStepRow>
                    </Fragment>
                  );
                })}
              </ol>
              </SortableContext>
              </DndContext>
            )}
          </div>

          {panel === "add" || panel === "edit" ? (
            <Modal title={panel === "add" ? addTitle : "Edit step"} onClose={function () { if (!busy) closePanel(); }} wide>
              {stepForm}
            </Modal>
          ) : null}
        </div>
      ) : null}
    </AppShell>
  );
}
