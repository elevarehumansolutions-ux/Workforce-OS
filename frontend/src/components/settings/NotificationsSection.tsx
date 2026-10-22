"use client";

import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import type { SectionProps } from "./types";

interface NotificationItem {
  id: string;
  category: string;
  title: string;
  read_at: string | null;
  created_at: string;
}

const KINDS: { name: string; text: string }[] = [
  { name: "Tasks", text: "A task is assigned to you, reassigned, or its deadline is close. Also the prompt asking if something is holding a task up." },
  { name: "Approvals", text: "Something is waiting for your decision, such as a block on a task or a skipped workflow step." },
  { name: "AI suggestions", text: "The AI has new suggestions for critical roles or KPIs to review." },
  { name: "System", text: "Account and organization notices." },
];

export default function NotificationsSection(props: SectionProps) {
  void props;
  const state = useLoad<NotificationItem[]>(
    "settings-notifications",
    function () {
      return apiFetch<NotificationItem[]>("/notifications", { method: "GET" });
    },
    "Couldn't load your recent notifications."
  );
  const recent = state.data ? state.data.slice(0, 5) : [];

  return (
    <div>
      <h3 className="text-base font-semibold text-white">Notifications</h3>
      <p className="mt-1 text-sm text-gray-500">What the system tells you about, and where you will see it.</p>

      <div className="mt-6 space-y-3">
        {KINDS.map(function (k) {
          return (
            <div key={k.name} className="rounded-xl border border-white/10 bg-[#0a0e1a] p-4">
              <p className="text-sm font-semibold text-white">{k.name}</p>
              <p className="mt-1 text-sm text-gray-400">{k.text}</p>
            </div>
          );
        })}
      </div>

      <p className="mt-4 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-gray-400">
        Notifications appear in the app. Choosing which ones you receive, or getting them by email, isn&apos;t available yet.
      </p>

      <div className="mt-8 border-t border-white/10 pt-6">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-white">Your latest notifications</h4>
          <Link href="/notifications" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
            See all
          </Link>
        </div>
        {state.loading ? <p className="mt-4 text-sm text-gray-400">Loading…</p> : null}
        {state.error ? <p className="mt-4 text-sm text-red-300">{state.error}</p> : null}
        {!state.loading && !state.error && recent.length === 0 ? <p className="mt-4 text-sm text-gray-500">You are all caught up.</p> : null}
        <ul className="mt-4 divide-y divide-white/5">
          {recent.map(function (n) {
            return (
              <li key={n.id} className="flex items-center justify-between gap-4 py-3 text-sm">
                <span className={n.read_at ? "text-gray-400" : "font-medium text-white"}>{n.title}</span>
                <span className="flex-shrink-0 text-xs text-gray-500">{formatDateTime(n.created_at)}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
