"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import { errorMessage } from "@/lib/tasks";

type Category = "ai_suggestion" | "approval_request" | "task" | "system";

interface NotificationItem {
  id: string;
  category: Category;
  title: string;
  body: string | null;
  link_type: string | null;
  link_id: string | null;
  read_at: string | null;
  created_at: string;
}

interface ListResult {
  key: string;
  items: NotificationItem[];
  error: string;
}

const FILTERS: { label: string; category: string; unread: boolean }[] = [
  { label: "All", category: "", unread: false },
  { label: "Unread", category: "", unread: true },
  { label: "Tasks", category: "task", unread: false },
  { label: "Approvals", category: "approval_request", unread: false },
  { label: "AI Suggestions", category: "ai_suggestion", unread: false },
  { label: "System", category: "system", unread: false },
];

function categoryLabel(category: string): string {
  if (category === "ai_suggestion") return "AI Suggestions";
  if (category === "approval_request") return "Approval";
  if (category === "task") return "Task";
  return "System";
}

function categoryBadge(category: string): string {
  if (category === "ai_suggestion") return "AI";
  if (category === "approval_request") return "A";
  if (category === "task") return "T";
  return "S";
}

function iconClasses(category: string): string {
  if (category === "ai_suggestion") return "bg-indigo-500/20 text-indigo-300";
  if (category === "approval_request") return "bg-amber-500/20 text-amber-300";
  if (category === "task") return "bg-cyan-500/20 text-cyan-300";
  return "bg-emerald-500/20 text-emerald-300";
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + (minutes === 1 ? " minute ago" : " minutes ago");
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + (hours === 1 ? " hour ago" : " hours ago");
  const days = Math.floor(hours / 24);
  if (days < 30) return days + (days === 1 ? " day ago" : " days ago");
  return new Date(iso).toLocaleDateString();
}

// Where a notification leads, based on what it points at. Returns null when
// there is nothing to open.
function destinationOf(n: NotificationItem): string | null {
  if (!n.link_type) return null;
  if (n.link_type === "task" && n.link_id) {
    // "Was something holding up: ...?" opens the task ready to be marked blocked.
    if (n.title.indexOf("Was something holding up") === 0) {
      return "/tasks/" + n.link_id + "?action=block";
    }
    return "/tasks/" + n.link_id;
  }
  // For a task block, link_id is the BLOCK id, not the task id.
  if (n.link_type === "task_block" && n.link_id) {
    return "/tasks/blocks?block=" + n.link_id;
  }
  if (n.link_type === "department" && n.link_id) {
    return "/tasks?department_id=" + n.link_id + "&status=open";
  }
  if (n.link_type === "ai_suggestions") {
    return "/onboarding/ai-suggestions";
  }
  return null;
}

export default function NotificationsPage() {
  const router = useRouter();
  const [filterIndex, setFilterIndex] = useState(0);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [readIds, setReadIds] = useState<string[]>([]);
  const [actionError, setActionError] = useState("");

  const filter = FILTERS[filterIndex];
  const key = [filterIndex, reloadCounter].join("|");
  const loading = result === null || result.key !== key;

  useEffect(
    function () {
      let cancelled = false;
      const params: string[] = [];
      if (filter.category) params.push("category=" + filter.category);
      if (filter.unread) params.push("unread=true");
      const path = "/notifications" + (params.length > 0 ? "?" + params.join("&") : "");

      apiFetch<NotificationItem[]>(path, { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setResult({ key: key, items: Array.isArray(res) ? res : [], error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({ key: key, items: [], error: errorMessage(err, "Couldn't load notifications. Check your connection and try again.") });
        });
      return function () {
        cancelled = true;
      };
    },
    [filter, key]
  );

  const items = result ? result.items : [];

  function isUnread(n: NotificationItem): boolean {
    return n.read_at === null && readIds.indexOf(n.id) === -1;
  }

  const unreadCount = items.filter(isUnread).length;

  async function openNotification(n: NotificationItem) {
    setActionError("");
    if (isUnread(n)) {
      setReadIds(readIds.concat([n.id]));
      try {
        await apiFetch("/notifications/" + n.id + "/read", { method: "POST" });
      } catch {
        // Not being able to mark it read shouldn't stop the person opening it.
      }
    }
    const destination = destinationOf(n);
    if (destination) router.push(destination);
  }

  async function markAllRead() {
    setActionError("");
    try {
      await apiFetch("/notifications/read-all", { method: "POST" });
      setReadIds(
        readIds.concat(
          items.map(function (n) {
            return n.id;
          })
        )
      );
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setActionError(errorMessage(err, "Couldn't mark everything as read. Try again."));
    }
  }

  return (
    <AppShell
      activeLabel="Dashboard"
      title="Notifications"
      breadcrumb="Dashboard > Notifications"
      actions={
        <button type="button" onClick={markAllRead} className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
          Mark all as read
        </button>
      }
    >
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map(function (f, index) {
            const isActive = filterIndex === index;
            return (
              <button
                key={f.label}
                type="button"
                onClick={function () {
                  setFilterIndex(index);
                }}
                className={
                  "rounded-lg px-4 py-2 text-sm font-medium " +
                  (isActive ? "bg-indigo-500 text-white" : "bg-[#0d1220] text-gray-400 hover:bg-white/5")
                }
              >
                {f.label}
              </button>
            );
          })}
        </div>
        {!loading && <span className="text-sm font-medium text-indigo-400">{unreadCount} unread</span>}
      </div>

      {actionError && (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{actionError}</div>
      )}

      <div className="mt-5 divide-y divide-white/5 rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
        {loading ? (
          <div className="p-10 text-center text-sm text-gray-500">Loading…</div>
        ) : result && result.error ? (
          <div className="p-10 text-center text-sm text-red-300">{result.error}</div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center text-sm text-gray-500">You are all caught up. New notifications will appear here.</div>
        ) : (
          items.map(function (n) {
            const unread = isUnread(n);
            const destination = destinationOf(n);
            return (
              <button
                key={n.id}
                type="button"
                onClick={function () {
                  openNotification(n);
                }}
                className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-white/5"
              >
                {unread ? (
                  <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-400" />
                ) : (
                  <span className="h-1.5 w-1.5 flex-shrink-0" />
                )}
                <span
                  className={
                    "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold " +
                    iconClasses(n.category)
                  }
                >
                  {categoryBadge(n.category)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className={"block text-sm " + (unread ? "font-semibold text-white" : "text-gray-300")}>{n.title}</span>
                  {n.body && <span className="mt-0.5 block text-xs text-gray-400">{n.body}</span>}
                  <span className="mt-0.5 block text-xs text-gray-500">{categoryLabel(n.category)}</span>
                </span>
                <span className="flex-shrink-0 text-xs text-gray-500">{timeAgo(n.created_at)}</span>
                {destination && (
                  <span className="flex-shrink-0 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white">Open</span>
                )}
              </button>
            );
          })
        )}
      </div>
    </AppShell>
  );
}
