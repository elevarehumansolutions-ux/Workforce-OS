"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { departmentName, errorMessage, formatDateTime, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext, PaginatedResponse } from "@/lib/tasks";
import { canManageTemplates, canStartCase } from "@/lib/workflow";
import type { WorkflowTemplate } from "@/lib/workflow";

interface ListResult {
  key: string;
  templates: WorkflowTemplate[];
  totalPages: number;
  total: number;
  error: string;
}

const PAGE_SIZE = 20;

export default function WorkflowTemplatesPage() {
  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [ctxError, setCtxError] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [busyId, setBusyId] = useState("");
  const [actionError, setActionError] = useState("");
  const [archiveHintId, setArchiveHintId] = useState("");

  const manage = ctx !== null && canManageTemplates(ctx);
  // Only people who can build templates see archived ones.
  const includeArchived = manage && showArchived;
  const key = [includeArchived, page, reloadCounter, ctx ? "ready" : "wait"].join("|");
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
        setCtxError(errorMessage(err, "Couldn't load workflow templates."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      if (!ctx) return;
      let cancelled = false;
      const path =
        "/workflow-templates?page=" + page + "&limit=" + PAGE_SIZE + (includeArchived ? "&include_archived=true" : "");
      apiFetch<PaginatedResponse<WorkflowTemplate>>(path, { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setResult({ key: key, templates: res.data, totalPages: res.pagination.total_pages, total: res.pagination.total, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            templates: [],
            totalPages: 1,
            total: 0,
            error: errorMessage(err, "Couldn't load workflow templates. Check your connection and try again."),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [ctx, page, includeArchived, key]
  );

  async function toggleArchive(t: WorkflowTemplate) {
    setActionError("");
    setArchiveHintId("");
    setBusyId(t.id);
    try {
      await apiFetch("/workflow-templates/" + t.id + (t.archived_at ? "/unarchive" : "/archive"), { method: "POST" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      // Already in that state means someone else just did it: refresh.
      if (err instanceof ApiError && (err.code === "WORKFLOW_TEMPLATE_ALREADY_ARCHIVED" || err.code === "WORKFLOW_TEMPLATE_NOT_ARCHIVED")) {
        setReloadCounter(reloadCounter + 1);
      } else {
        setActionError(errorMessage(err, "Couldn't change this template. Check your connection and try again."));
      }
    } finally {
      setBusyId("");
    }
  }

  async function remove(t: WorkflowTemplate) {
    if (!window.confirm('Delete the template "' + t.name + '" and all its steps? This can\'t be undone.')) return;
    setActionError("");
    setArchiveHintId("");
    setBusyId(t.id);
    try {
      await apiFetch("/workflow-templates/" + t.id, { method: "DELETE" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setActionError(errorMessage(err, "Couldn't delete this template. Check your connection and try again."));
      // Cases still running: offer Archive instead.
      if (err instanceof ApiError && err.code === "RESOURCE_IN_USE") setArchiveHintId(t.id);
    } finally {
      setBusyId("");
    }
  }

  const templates = result ? result.templates : [];
  const buttonClass = "rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5 disabled:opacity-50";

  return (
    <AppShell
      activeLabel="Workflow"
      title="Workflow templates"
      breadcrumb="Dashboard > Workflow > Templates"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/workflow/tracker" className="rounded-lg border border-indigo-500 px-4 py-2 text-sm font-medium text-indigo-400 hover:bg-indigo-500/10">
            Cases
          </Link>
          {ctx && canStartCase(ctx) ? (
            <Link href="/workflow/start" className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
              Start workflow
            </Link>
          ) : null}
          {manage ? (
            <Link href="/workflow/new-template" className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
              + New template
            </Link>
          ) : null}
        </div>
      }
    >
      {ctxError ? <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{ctxError}</div> : null}

      {manage ? (
        <label className="mb-4 flex items-center gap-2 text-sm text-gray-400">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={function (e) {
              setShowArchived(e.target.checked);
              setPage(1);
            }}
          />
          Show archived templates
        </label>
      ) : null}

      {actionError ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {actionError}
          {archiveHintId ? (
            <button
              type="button"
              onClick={function () {
                const target = templates.find(function (t) {
                  return t.id === archiveHintId;
                });
                if (target) toggleArchive(target);
              }}
              className="ml-3 rounded border border-red-300/40 px-2 py-0.5 text-xs font-medium text-red-200 hover:bg-red-500/10"
            >
              Archive it instead
            </button>
          ) : null}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {!loading && result && result.error ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{result.error}</div>
      ) : null}

      {!loading && ctx && result && !result.error ? (
        <div className="overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-5 py-3 font-medium">Template</th>
                <th className="px-5 py-3 font-medium">Owned by</th>
                <th className="px-5 py-3 font-medium">Last edited</th>
                <th className="px-5 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {templates.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-gray-500">
                    {manage ? "No templates yet. Create one to get started." : "No workflow templates are available yet."}
                  </td>
                </tr>
              ) : (
                templates.map(function (t) {
                  const archived = t.archived_at !== null;
                  return (
                    <tr key={t.id} className="border-b border-white/5 align-top">
                      <td className="px-5 py-4">
                        <Link href={"/workflow/templates/" + t.id} className="font-medium text-white hover:text-indigo-300">
                          {t.name}
                        </Link>
                        {archived ? (
                          <span className="ml-2 rounded bg-gray-500/20 px-2 py-0.5 text-xs font-medium text-gray-400">Archived</span>
                        ) : null}
                      </td>
                      <td className="px-5 py-4 text-gray-400">{departmentName(ctx, t.department_id)}</td>
                      <td className="px-5 py-4 text-gray-400">{formatDateTime(t.updated_at)}</td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap justify-end gap-2">
                          <Link href={"/workflow/templates/" + t.id} className={buttonClass}>
                            {manage ? "Open & edit steps" : "View steps"}
                          </Link>
                          {!archived && canStartCase(ctx) ? (
                            <Link href={"/workflow/start?template=" + t.id} className={buttonClass}>
                              Start
                            </Link>
                          ) : null}
                          {manage ? (
                            <button type="button" disabled={busyId === t.id} onClick={function () { toggleArchive(t); }} className={buttonClass}>
                              {archived ? "Unarchive" : "Archive"}
                            </button>
                          ) : null}
                          {manage ? (
                            <button
                              type="button"
                              disabled={busyId === t.id}
                              onClick={function () {
                                remove(t);
                              }}
                              className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                            >
                              Delete
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      ) : null}

      {result && result.totalPages > 1 ? (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {page} of {result.totalPages} · {result.total} templates
          </span>
          <div className="flex gap-2">
            <button type="button" disabled={page <= 1} onClick={function () { setPage(page - 1); }} className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40">
              Previous
            </button>
            <button type="button" disabled={page >= result.totalPages} onClick={function () { setPage(page + 1); }} className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40">
              Next
            </button>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
