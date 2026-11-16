"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import BlockReviewActions from "@/components/BlockReviewActions";
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

// Blocks that belong to the same task, kept together in the order they first appear (the list is newest first).
function groupByTask(blocks: ReviewBlock[]): ReviewBlock[][] {
  const groups: ReviewBlock[][] = [];
  const indexByTask: Record<string, number> = {};
  for (const b of blocks) {
    if (indexByTask[b.task_id] === undefined) {
      indexByTask[b.task_id] = groups.length;
      groups.push([]);
    }
    groups[indexByTask[b.task_id]].push(b);
  }
  return groups;
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

  function changeTab(next: ReviewStatus) {
    setTab(next);
    setPage(1);
  }

  const blocks = result ? result.blocks : [];
  // Waiting blocks of one task are decided together, so they are shown as one card.
  const groups = tab === "pending" ? groupByTask(blocks) : blocks.map(function (b) { return [b]; });

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
        a block, YOU choose how much extra time the task gets, and its deadline moves later by that amount straight
        away. The block then ends and the task is open again. If you reject it, the task keeps its deadline and the
        block ends. Either decision is final, so if the cause persists the person raises a new block. If a task has
        several blocks waiting, one decision covers all of them. You can also decide from the task&apos;s own page.
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
          groups.map(function (group) {
            const first = group[0];
            const highlighted = group.some(function (b) {
              return b.id === highlightId;
            });
            return (
              <div
                key={first.task_id + "|" + first.id}
                className={
                  "rounded-2xl border bg-[#0d1220]/80 p-5 shadow-xl " +
                  (highlighted ? "border-indigo-500/60" : "border-white/10")
                }
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={"/tasks/" + first.task_id} className="text-base font-semibold text-white hover:text-indigo-300">
                      {first.task_title}
                    </Link>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {ctx ? departmentName(ctx, first.task_department_id) : "Department"} · Deadline{" "}
                      {formatDateTime(first.task_due_at)}
                    </p>
                  </div>
                  {tab !== "pending" ? (
                    <span className={"rounded-full px-3 py-1 text-xs font-medium " + reviewStatusClasses(first.review_status)}>
                      {reviewStatusLabel(first.review_status)}
                    </span>
                  ) : null}
                </div>

                {group.map(function (b) {
                  return (
                    <div key={b.id} className="mt-3">
                      <div className="rounded-lg bg-white/5 p-3 text-sm">
                        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{blockCategoryLabel(b.category)}</p>
                        <p className="mt-1 whitespace-pre-wrap text-gray-200">{b.reason}</p>
                      </div>
                      <p className="mt-2 text-xs text-gray-500">
                        Blocked {formatDateTime(b.blocked_at)}
                        {b.unblocked_at ? " · Ended " + formatDateTime(b.unblocked_at) : ""} · Length: {lengthOf(b)}
                        {b.reviewed_at ? " · Reviewed " + formatDateTime(b.reviewed_at) : ""}
                      </p>
                      {b.estimated_seconds ? (
                        <p className="mt-1 text-xs text-gray-400">The person asked for {formatDuration(b.estimated_seconds)} more.</p>
                      ) : null}
                      {b.review_status === "approved" && b.granted_seconds ? (
                        <p className="mt-1 text-xs text-emerald-300">Extra time given: {formatDuration(b.granted_seconds)}.</p>
                      ) : null}
                    </div>
                  );
                })}

                {tab === "pending" && (
                  <div className="mt-4">
                    <BlockReviewActions
                      block={first}
                      taskDueAt={first.task_due_at}
                      taskApprovedSeconds={first.task_approved_blocked_seconds}
                      waitingCount={group.length}
                      onDecided={function () {
                        setReloadCounter(reloadCounter + 1);
                      }}
                    />
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
