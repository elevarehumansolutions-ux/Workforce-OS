"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import {
  activeEmployees,
  canCreateTasks,
  canPickAssignee,
  errorMessage,
  fullName,
  loadCaller,
  localInputToIso,
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
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    const body: Record<string, string> = { department_id: departmentId, title: trimmedTitle };
    if (description.trim()) body.description = description.trim();
    if (dueIso) body.due_at = dueIso;
    if (kpiId) body.kpi_id = kpiId;
    if (pickerAllowed && assigneeId) body.assigned_to_employee_id = assigneeId;

    setSubmitting(true);
    try {
      const created = await apiFetch<Task>("/tasks", { method: "POST", body: body });
      router.push("/tasks/" + created.id);
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
                setKpiId("");
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
              {errors.due_at ? <p className="mt-1 text-xs text-red-400">{errors.due_at}</p> : null}
            </div>

            <div>
              <label htmlFor="kpi" className="mb-2 block text-sm font-medium text-gray-200">
                Linked KPI <span className="text-gray-500">(optional)</span>
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
                <option value="">{departmentId ? "No linked KPI" : "Choose a department first"}</option>
                {departmentKpis.map(function (k) {
                  return (
                    <option key={k.id} value={k.id}>
                      {k.name}
                    </option>
                  );
                })}
              </select>
              {errors.kpi_id ? <p className="mt-1 text-xs text-red-400">{errors.kpi_id}</p> : null}
            </div>
          </div>

          {departmentId ? (
            pickerAllowed ? (
              <div>
                <label htmlFor="assignee" className="mb-2 block text-sm font-medium text-gray-200">
                  Assign to
                </label>
                <select
                  id="assignee"
                  value={assigneeId}
                  onChange={function (e) {
                    setAssigneeId(e.target.value);
                  }}
                  className={inputClass}
                >
                  <option value="">Leave unassigned for now</option>
                  {activeEmployees(ctx).map(function (emp) {
                    return (
                      <option key={emp.id} value={emp.id}>
                        {fullName(emp)}
                      </option>
                    );
                  })}
                </select>
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

          <div className="flex items-center justify-between border-t border-white/10 pt-5">
            <Link href="/tasks" className="text-sm font-medium text-gray-400 hover:text-gray-200">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Creating…" : "Create task"}
            </button>
          </div>
        </form>
      ) : null}
    </AppShell>
  );
}
