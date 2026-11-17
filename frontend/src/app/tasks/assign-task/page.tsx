"use client";

import { useEffect, useRef, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import DeadlineHint from "@/components/DeadlineHint";
import DeadlineQuickPicks from "@/components/DeadlineQuickPicks";
import PersonSelect from "@/components/PersonSelect";
import {
  peopleOfDepartment,
  canCreateTasks,
  canPickAssignee,
  errorMessage,
  kpiDetail,
  loadCaller,
  localInputToIso,
  onlyKpiOf,
  roleLabel,
} from "@/lib/tasks";
import type { CallerContext, Task } from "@/lib/tasks";

const inputClass =
  "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500";

export default function AssignTaskPage() {
  const router = useRouter();
  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");

  const [departmentId, setDepartmentId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueLocal, setDueLocal] = useState("");
  const [kpiId, setKpiId] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  // Other departments that get the same task (each its own copy, finished on its own).
  const [extras, setExtras] = useState<{ department_id: string; assignee: string }[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // Set by the "Create and add another" button just before the form is submitted. A ref, not state,
  // because the submit handler must see the value from the click that started it.
  const addAnotherRef = useRef(false);
  const [justCreated, setJustCreated] = useState("");

  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function (err) {
        if (cancelled) return;
        setCtxError(errorMessage(err, "Couldn't load the form. Check your connection and try again."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  const selectedDepartment = ctx
    ? ctx.departments.find(function (d) {
        return d.id === departmentId;
      })
    : undefined;
  const pickerAllowed = ctx !== null && departmentId !== "" && canPickAssignee(ctx, departmentId);
  const departmentKpis = ctx
    ? ctx.kpis.filter(function (k) {
        return k.department_id === departmentId;
      })
    : [];

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ctx) return;
    setFormError("");
    setJustCreated("");

    const newErrors: Record<string, string> = {};
    const trimmedTitle = title.trim();
    if (!departmentId) newErrors.department_id = "Choose the department that will do the work.";
    if (!trimmedTitle) newErrors.title = "Give the task a title.";
    if (trimmedTitle.length > 255) newErrors.title = "The title can be at most 255 characters.";
    let dueIso: string | null = null;
    if (dueLocal) {
      dueIso = localInputToIso(dueLocal);
      if (!dueIso) newErrors.due_at = "That deadline isn't a valid date and time.";
    }
    for (const x of extras) {
      if (!x.department_id) newErrors.also_for = "Choose a department for each extra department, or remove the empty one.";
    }
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    const body: Record<string, unknown> = { department_id: departmentId, title: trimmedTitle };
    if (description.trim()) body.description = description.trim();
    if (dueIso) body.due_at = dueIso;
    if (kpiId) body.kpi_id = kpiId;
    if (pickerAllowed && assigneeId) body.assigned_to_employee_id = assigneeId;
    if (extras.length > 0) {
      // A person can only be named for a department the caller may pick people for; otherwise that
      // department's head receives it (the same rule as for a task on its own).
      body.also_for = extras.map(function (x) {
        const item: Record<string, string> = { department_id: x.department_id };
        if (x.assignee && canPickAssignee(ctx, x.department_id)) item.assigned_to_employee_id = x.assignee;
        return item;
      });
    }

    setSubmitting(true);
    try {
      const created = await apiFetch<Task>("/tasks", { method: "POST", body: body });
      if (addAnotherRef.current) {
        // Keep the department, goal and deadline (a head usually hands out several similar tasks);
        // clear what is different each time.
        setJustCreated("Created: " + created.title);
        setTitle("");
        setDescription("");
        setAssigneeId("");
        setExtras([]);
        setSubmitting(false);
      } else {
        router.push("/tasks/" + created.id);
      }
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError(errorMessage(err, "Couldn't create the task. Check your connection and try again."));
      }
      setSubmitting(false);
    }
  }

  const allowed = ctx !== null && canCreateTasks(ctx);

  return (
    <AppShell
      activeLabel="Tasks"
      title="Assign task"
      breadcrumb="Dashboard > Tasks > Assign task"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
    >
      {ctxError ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div>
      ) : null}
      {!ctx && !ctxError ? <p className="text-sm text-gray-400">Loading…</p> : null}

      {ctx && !allowed ? (
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
          <p className="text-base font-semibold">You can&apos;t assign tasks</p>
          <p className="mt-2 max-w-xl text-sm text-gray-400">
            Tasks can be created by HR administrators, managers and department heads. Ask one of them if something
            needs doing.
          </p>
          <Link href="/tasks" className="mt-4 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300">
            Back to tasks
          </Link>
        </div>
      ) : null}

      {ctx && allowed ? (
        <form
          onSubmit={handleSubmit}
          className="max-w-2xl space-y-5 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl"
        >
          {justCreated ? (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
              {justCreated}. The department, goal and deadline are kept for the next one.
            </div>
          ) : null}
          {formError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {formError}
            </div>
          ) : null}

          <div>
            <label htmlFor="department" className="mb-2 block text-sm font-medium text-gray-200">
              Department doing the work
            </label>
            <select
              id="department"
              value={departmentId}
              onChange={function (e) {
                setDepartmentId(e.target.value);
                // A department with just one KPI has it chosen for the person; otherwise they choose.
                setKpiId(onlyKpiOf(ctx, e.target.value));
                setAssigneeId("");
              }}
              className={inputClass}
            >
              <option value="">Select department…</option>
              {ctx.departments.map(function (d) {
                return (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                );
              })}
            </select>
            {errors.department_id ? <p className="mt-1 text-xs text-red-400">{errors.department_id}</p> : null}
          </div>

          <div>
            <label htmlFor="title" className="mb-2 block text-sm font-medium text-gray-200">
              Task title
            </label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={function (e) {
                setTitle(e.target.value);
              }}
              placeholder="e.g. Prepare the Q4 sales forecast"
              className={inputClass}
            />
            {errors.title ? <p className="mt-1 text-xs text-red-400">{errors.title}</p> : null}
          </div>

          <div>
            <label htmlFor="description" className="mb-2 block text-sm font-medium text-gray-200">
              Description <span className="text-gray-500">(optional)</span>
            </label>
            <textarea
              id="description"
              rows={4}
              value={description}
              onChange={function (e) {
                setDescription(e.target.value);
              }}
              className={inputClass}
            />
            {errors.description ? <p className="mt-1 text-xs text-red-400">{errors.description}</p> : null}
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label htmlFor="due" className="mb-2 block text-sm font-medium text-gray-200">
                Deadline <span className="text-gray-500">(optional)</span>
              </label>
              <input
                id="due"
                type="datetime-local"
                value={dueLocal}
                onChange={function (e) {
                  setDueLocal(e.target.value);
                }}
                className={inputClass}
              />
              <DeadlineQuickPicks onPick={setDueLocal} />
              <DeadlineHint value={dueLocal} />
              {errors.due_at ? <p className="mt-1 text-xs text-red-400">{errors.due_at}</p> : null}
            </div>

            <div>
              <label htmlFor="kpi" className="mb-2 block text-sm font-medium text-gray-200">
                Which goal (KPI) does this move forward? <span className="text-gray-500">(optional)</span>
              </label>
              <select
                id="kpi"
                value={kpiId}
                disabled={!departmentId}
                onChange={function (e) {
                  setKpiId(e.target.value);
                }}
                className={inputClass + " disabled:opacity-60"}
              >
                <option value="">{departmentId ? "Not linked: it won't count in performance scores" : "Choose a department first"}</option>
                {departmentKpis.map(function (k) {
                  return (
                    <option key={k.id} value={k.id}>
                      {k.name}
                    </option>
                  );
                })}
              </select>
              {kpiId ? (
                <p className="mt-1 text-xs text-gray-400">
                  {kpiDetail(departmentKpis.find(function (k) { return k.id === kpiId; }))}
                </p>
              ) : null}
              {departmentId && departmentKpis.length === 1 && kpiId === departmentKpis[0].id ? (
                <p className="mt-1 text-xs text-gray-500">
                  This is the only KPI of this department, so it is chosen for you. Pick the empty option to unlink it.
                </p>
              ) : null}
              {departmentId && departmentKpis.length === 0 ? (
                <p className="mt-1 text-xs text-gray-500">This department has no KPIs yet, so the task cannot count toward a score.</p>
              ) : null}
              {errors.kpi_id ? <p className="mt-1 text-xs text-red-400">{errors.kpi_id}</p> : null}
            </div>
          </div>

          {departmentId ? (
            pickerAllowed ? (
              <div>
                <label htmlFor="assignee" className="mb-2 block text-sm font-medium text-gray-200">
                  Assign to
                </label>
                <PersonSelect
                  id="assignee"
                  people={peopleOfDepartment(ctx, departmentId)}
                  positions={ctx.positions}
                  departments={ctx.departments}
                  value={assigneeId}
                  onChange={setAssigneeId}
                  emptyLabel="Leave unassigned for now"
                  className={inputClass}
                />
                {errors.assigned_to_employee_id ? (
                  <p className="mt-1 text-xs text-red-400">{errors.assigned_to_employee_id}</p>
                ) : null}
              </div>
            ) : (
              <div className="rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-gray-400">
                {selectedDepartment && selectedDepartment.head_employee_id
                  ? "This task is for another department, so it goes to that department's head, who can hand it on."
                  : "This task is for another department that has no head yet. It will be created unassigned and HR will be notified."}
              </div>
            )
          ) : null}

          {departmentId ? (
            <div className="rounded-xl border border-white/10 p-4">
              <p className="text-sm font-medium text-gray-200">Also needs other departments (optional)</p>
              <p className="mt-1 text-xs text-gray-500">
                Add a department that must do its own part of this task. Each one gets its own copy with the same title
                and deadline, is told and emailed, and finishes it on its own. The copies are linked, so each can see who
                else is on it.
              </p>
              {extras.map(function (x, index) {
                const pick = canPickAssignee(ctx, x.department_id);
                return (
                  <div key={index} className="mt-3 grid gap-3 border-t border-white/10 pt-3 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-xs text-gray-500">Department</label>
                      <select
                        value={x.department_id}
                        onChange={function (e) {
                          setExtras(
                            extras.map(function (y, i) {
                              return i === index ? { department_id: e.target.value, assignee: "" } : y;
                            })
                          );
                        }}
                        className={inputClass}
                      >
                        <option value="">Select department…</option>
                        {ctx.departments
                          .filter(function (d) {
                            return d.id !== departmentId;
                          })
                          .map(function (d) {
                            return (
                              <option key={d.id} value={d.id}>
                                {d.name}
                              </option>
                            );
                          })}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-gray-500">Assign to</label>
                      {x.department_id && pick ? (
                        <PersonSelect
                          people={peopleOfDepartment(ctx, x.department_id)}
                          positions={ctx.positions}
                          departments={ctx.departments}
                          value={x.assignee}
                          onChange={function (id) {
                            setExtras(
                              extras.map(function (y, i) {
                                return i === index ? { ...y, assignee: id } : y;
                              })
                            );
                          }}
                          emptyLabel="Leave unassigned for now"
                          className={inputClass}
                        />
                      ) : (
                        <p className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-xs text-gray-400">
                          {x.department_id
                            ? "It goes to that department's head (or HR if it has none), who hands it on."
                            : "Choose the department first."}
                        </p>
                      )}
                    </div>
                    <div className="sm:col-span-2">
                      <button
                        type="button"
                        onClick={function () {
                          setExtras(
                            extras.filter(function (_y, i) {
                              return i !== index;
                            })
                          );
                        }}
                        className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/10"
                      >
                        Remove this department
                      </button>
                    </div>
                  </div>
                );
              })}
              {errors.also_for ? <p className="mt-2 text-xs text-red-400">{errors.also_for}</p> : null}
              <button
                type="button"
                disabled={extras.length >= 5}
                onClick={function () {
                  setExtras(extras.concat([{ department_id: "", assignee: "" }]));
                }}
                className="mt-3 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                + Add a department
              </button>
            </div>
          ) : null}

          <div className="flex items-center justify-between border-t border-white/10 pt-5">
            <Link href="/tasks" className="text-sm font-medium text-gray-400 hover:text-gray-200">
              Cancel
            </Link>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={submitting}
                onClick={function () {
                  addAnotherRef.current = true;
                }}
                className="rounded-lg border border-indigo-400/50 px-5 py-3 text-sm font-semibold text-indigo-200 transition hover:bg-indigo-500/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Create and add another
              </button>
              <button
                type="submit"
                disabled={submitting}
                onClick={function () {
                  addAnotherRef.current = false;
                }}
                className="rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Creating…" : "Create task"}
              </button>
            </div>
          </div>
        </form>
      ) : null}
    </AppShell>
  );
}
