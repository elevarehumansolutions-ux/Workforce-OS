"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { errorMessage, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext } from "@/lib/tasks";
import { canManageTemplates } from "@/lib/workflow";
import type { WorkflowTemplate } from "@/lib/workflow";

export default function NewWorkflowTemplatePage() {
  const router = useRouter();
  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [name, setName] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function (err) {
        if (cancelled) return;
        setCtxError(errorMessage(err, "Couldn't load your departments."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  async function create() {
    setError("");
    if (!name.trim()) {
      setError("Give the template a name.");
      return;
    }
    if (!departmentId) {
      setError("Choose the department that owns this template.");
      return;
    }
    setSaving(true);
    try {
      const created = await apiFetch<WorkflowTemplate>("/workflow-templates", {
        method: "POST",
        body: { name: name.trim(), department_id: departmentId },
      });
      // A new template has no steps yet; the next screen is where they are added.
      router.push("/workflow/templates/" + created.id);
    } catch (err) {
      setError(errorMessage(err, "Couldn't create the template. Check your connection and try again."));
      setSaving(false);
    }
  }

  const inputClass = "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500";

  return (
    <AppShell
      activeLabel="Workflow"
      title="New workflow template"
      breadcrumb="Dashboard > Workflow > Templates > New"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/workflow/templates" className="text-sm font-medium text-gray-400 hover:text-gray-200">
          Back to templates
        </Link>
      }
    >
      {ctxError ? <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div> : null}
      {!ctx && !ctxError ? <p className="text-sm text-gray-400">Loading…</p> : null}

      {ctx && !canManageTemplates(ctx) ? (
        <div className="max-w-xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-sm text-gray-400">
          Only HR administrators and managers can create workflow templates.
        </div>
      ) : null}

      {ctx && canManageTemplates(ctx) ? (
        <div className="max-w-2xl space-y-5 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6">
          {error ? <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div> : null}
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-200">Template name</label>
            <input
              type="text"
              maxLength={200}
              value={name}
              onChange={function (e) {
                setName(e.target.value);
              }}
              placeholder="e.g. Client Onboarding"
              className={inputClass}
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-200">Owning department</label>
            <select
              value={departmentId}
              onChange={function (e) {
                setDepartmentId(e.target.value);
              }}
              className={inputClass}
            >
              <option value="">Choose a department</option>
              {ctx.departments.map(function (d) {
                return (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                );
              })}
            </select>
            <p className="mt-1 text-xs text-gray-500">Each step can still be done by a different department.</p>
          </div>
          <p className="text-xs text-gray-500">You&apos;ll add the steps on the next screen.</p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={create}
              className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? "Creating…" : "Create template"}
            </button>
            <Link href="/workflow/templates" className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5">
              Cancel
            </Link>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
