"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import AppShell from "@/components/AppShell";
import {
  blockCategoryLabel,
  departmentName,
  errorMessage,
  formatDateTime,
  formatDuration,
  loadCaller,
  reviewStatusClasses,
  reviewStatusLabel,
  roleLabel,
} from "@/lib/tasks";
import type { CallerContext, PaginatedResponse, ReviewBlock, ReviewStatus } from "@/lib/tasks";

interface ListResult {
  key: string;
  blocks: ReviewBlock[];
  total: number;
  totalPages: number;
  error: string;
}

const PAGE_SIZE = 20;

const TABS: { value: ReviewStatus; label: string }[] = [
  { value: "pending", label: "Waiting for review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

function lengthOf(block: ReviewBlock): string {
  if (!block.unblocked_at) return "Still blocked";
  const seconds = (new Date(block.unblocked_at).getTime() - new Date(block.blocked_at).getTime()) / 1000;
  return formatDuration(seconds);
}

function BlocksContent() {
  // A notification opens this screen on one block: /tasks/blocks?block=<id>
  const searchParams = useSearchParams();
  const highlightId = searchParams.get("block") || "";

  const [ctx, setCtx] = useState<CallerContext | null>(null);
  const [tab, setTab] = useState<ReviewStatus>("pending");
  const [page, setPage] = useState(1);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [busyId, setBusyId] = useState("");
  const [actionError, setActionError] = useState("");

  const key = [tab, page, reloadCounter].join("|");
  const loading = result === null || result.key !== key;

  // The names of departments and the person's role are nice to have; the
  // list works without them.
  useEffect(function () {
    let cancelled = false;
    loadCaller()
      .then(function (loaded) {
        if (cancelled) return;
        setCtx(loaded);
      })
      .catch(function () {
        // leave ctx empty
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      let cancelled = false;
      const path = "/task-blocks?review_status=" + tab + "&page=" + page + "&limit=" + PAGE_SIZE;
      apiFetch<PaginatedResponse<ReviewBlock>>(path, { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setResult({
            key: key,
            blocks: res.data,
            total: res.pagination.total,
            totalPages: res.pagination.total_pages,
            error: "",
          });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            blocks: [],
            total: 0,
            totalPages: 1,
            error: errorMessage(err, "Couldn't load blocks. Check your connection and try again."),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [tab, page, key]
  );

  async function review(block: ReviewBlock, decision: "approve" | "reject") {
    setActionError("");
    setBusyId(block.id);
    try {
      await apiFetch("/task-blocks/" + block.id + "/" + decision, { method: "POST" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      if (err instanceof ApiError && err.code === "TASK_BLOCK_NOT_FOUND") {
        setActionError("That block wasn't found. It may be outside your reach now.");
      } else if (err instanceof ApiError && err.code === "TASK_BLOCK_ALREADY_REVIEWED") {
        setActionError("This block has already been reviewed. The list has been refreshed.");
        setReloadCounter(reloadCounter + 1);
      } else {
        setActionError(errorMessage(err, "Couldn't save your decision. Check your connection and try again."));
      }
    } finally {
      setBusyId("");
    }
  }

  function changeTab(next: ReviewStatus) {
    setTab(next);
    setPage(1);
    setActionError("");
  }

  const blocks = result ? result.blocks : [];

  return (
    <AppShell
      activeLabel="Tasks"
      title="Blocks to review"
      breadcrumb="Dashboard > Tasks > Blocks to review"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/tasks" className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/5">
          Back to tasks
        </Link>
      }
    >
      <div className="rounded-xl border border-white/10 bg-[#0d1220]/80 p-4 text-sm text-gray-400">
        When someone says a task is stuck because of something outside their hands, it shows up here. If you approve
        a block, the time it lasted is given back by moving that task&apos;s real deadline later. If you reject it, the
        task is judged as if it was never blocked. Either decision is final.
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {TABS.map(function (t) {
          const active = tab === t.value;
          return (
            <button
              key={t.value}
              type="button"
              onClick={function () {
                changeTab(t.value);
              }}
              className={
                "rounded-lg px-4 py-2 text-sm font-medium " +
                (active ? "bg-indigo-500 text-white" : "bg-[#0d1220] text-gray-400 hover:bg-white/5")
              }
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {actionError && (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{actionError}</div>
      )}

      <div className="mt-5 space-y-3">
        {loading ? (
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center text-sm text-gray-500">Loading…</div>
        ) : result && result.error ? (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-300">{result.error}</div>
        ) : blocks.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center text-sm text-gray-500">
            {tab === "pending" ? "Nothing is waiting for your review." : "No " + tab + " blocks yet."}
          </div>
        ) : (
          blocks.map(function (b) {
            const highlighted = b.id === highlightId;
            return (
              <div
                key={b.id}
                className={
                  "rounded-2xl border bg-[#0d1220]/80 p-5 shadow-xl " +
                  (highlighted ? "border-indigo-500/60" : "border-white/10")
                }
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-base font-semibold">{b.task_title}</p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {ctx ? departmentName(ctx, b.task_department_id) : "Department"} · Deadline {formatDateTime(b.task_due_at)}
                    </p>
                  </div>
                  <span className={"rounded-full px-3 py-1 text-xs font-medium " + reviewStatusClasses(b.review_status)}>
                    {reviewStatusLabel(b.review_status)}
                  </span>
                </div>

                <div className="mt-3 rounded-lg bg-white/5 p-3 text-sm">
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{blockCategoryLabel(b.category)}</p>
                  <p className="mt-1 whitespace-pre-wrap text-gray-200">{b.reason}</p>
                </div>

                <p className="mt-3 text-xs text-gray-500">
                  Blocked {formatDateTime(b.blocked_at)}
                  {b.unblocked_at ? " · Unblocked " + formatDateTime(b.unblocked_at) : ""} · Length: {lengthOf(b)}
                  {b.reviewed_at ? " · Reviewed " + formatDateTime(b.reviewed_at) : ""}
                </p>

                {b.review_status === "pending" && (
                  <div className="mt-4 flex gap-3">
                    <button
                      type="button"
                      disabled={busyId === b.id}
                      onClick={function () {
                        review(b, "approve");
                      }}
                      className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={busyId === b.id}
                      onClick={function () {
                        review(b, "reject");
                      }}
                      className="rounded-lg border border-red-500/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {result && result.totalPages > 1 && (
        <div className="mt-5 flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {page} of {result.totalPages} · {result.total} in total
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={function () {
                setPage(page - 1);
              }}
              className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= result.totalPages}
              onClick={function () {
                setPage(page + 1);
              }}
              className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default function BlocksPage() {
  return (
    <Suspense fallback={null}>
      <BlocksContent />
    </Suspense>
  );
}
