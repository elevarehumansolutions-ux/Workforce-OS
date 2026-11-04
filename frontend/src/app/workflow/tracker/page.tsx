"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { errorMessage, fetchAllPages, formatDateTime, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext, PaginatedResponse } from "@/lib/tasks";
import { canStartCase, caseStatusClasses, caseStatusLabel } from "@/lib/workflow";
import type { CaseStatus, WorkflowCase, WorkflowTemplate } from "@/lib/workflow";

interface ListResult {
  key: string;
  cases: WorkflowCase[];
  total: number;
  totalPages: number;
  error: string;
}

const PAGE_SIZE = 20;

const TABS: { value: CaseStatus; label: string }[] = [
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export default function WorkflowCasesPage() {
  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [status, setStatus] = useState<CaseStatus>("in_progress");
  const [templateId, setTemplateId] = useState("");
  const [page, setPage] = useState(1);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [result, setResult] = useState<ListResult | null>(null);

  const key = [status, templateId, page].join("|");
  const loading = result === null || result.key !== key;

  // Names for the template column and the filter; the list works without them.
  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function () {
        // leave empty
      });
    fetchAllPages<WorkflowTemplate>("/workflow-templates?include_archived=true")
      .then(function (list) {
        if (cancelled) return;
        setTemplates(list);
      })
      .catch(function () {
        // leave empty
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      let cancelled = false;
      let path = "/workflow-instances?status=" + status + "&page=" + page + "&limit=" + PAGE_SIZE;
      if (templateId) path = path + "&template_id=" + templateId;
      apiFetch<PaginatedResponse<WorkflowCase>>(path, { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setResult({ key: key, cases: res.data, total: res.pagination.total, totalPages: res.pagination.total_pages, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({ key: key, cases: [], total: 0, totalPages: 1, error: errorMessage(err, "Couldn't load cases. Check your connection and try again.") });
        });
      return function () {
        cancelled = true;
      };
    },
    [status, templateId, page, key]
  );

  function templateName(id: string): string {
    for (const t of templates) {
      if (t.id === id) return t.name;
    }
    return "Template";
  }

  const cases = result ? result.cases : [];

  return (
    <AppShell
      activeLabel="Workflow"
      title="Workflow cases"
      breadcrumb="Dashboard > Workflow > Cases"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <div className="flex items-center gap-2">
          <Link href="/workflow/templates" className="rounded-lg border border-indigo-500 px-4 py-2 text-sm font-medium text-indigo-400 hover:bg-indigo-500/10">
            Templates
          </Link>
          {ctx && canStartCase(ctx) ? (
            <Link href="/workflow/start" className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
              Start workflow
            </Link>
          ) : null}
        </div>
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {TABS.map(function (t) {
            const active = status === t.value;
            return (
              <button
                key={t.value}
                type="button"
                onClick={function () {
                  setStatus(t.value);
                  setPage(1);
                }}
                className={"rounded-lg px-4 py-2 text-sm font-medium " + (active ? "bg-indigo-500 text-white" : "bg-[#0d1220] text-gray-400 hover:bg-white/5")}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <select
          value={templateId}
          onChange={function (e) {
            setTemplateId(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500"
        >
          <option value="">All templates</option>
          {templates.map(function (t) {
            return (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            );
          })}
        </select>
      </div>

      <div className="mt-5 overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-5 py-3 font-medium">Case</th>
              <th className="px-5 py-3 font-medium">Template</th>
              <th className="px-5 py-3 font-medium">Started</th>
              <th className="px-5 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-5 py-10 text-center text-gray-500">
                  Loading…
                </td>
              </tr>
            ) : result && result.error ? (
              <tr>
                <td colSpan={4} className="px-5 py-10 text-center text-red-300">
                  {result.error}
                </td>
              </tr>
            ) : cases.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-10 text-center text-gray-500">
                  No cases to show here. You see the cases you started, the ones you have a task in, and the ones in your department.
                </td>
              </tr>
            ) : (
              cases.map(function (c) {
                return (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-5 py-4">
                      <Link href={"/workflow/case-detail?id=" + c.id} className="font-medium text-white hover:text-indigo-300">
                        {c.subject}
                      </Link>
                    </td>
                    <td className="px-5 py-4 text-gray-400">{templateName(c.workflow_template_id)}</td>
                    <td className="px-5 py-4 text-gray-400">{formatDateTime(c.started_at)}</td>
                    <td className="px-5 py-4">
                      <span className={"rounded px-2 py-0.5 text-xs font-medium " + caseStatusClasses(c.status)}>{caseStatusLabel(c.status)}</span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {result && result.totalPages > 1 ? (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {page} of {result.totalPages} · {result.total} cases
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
