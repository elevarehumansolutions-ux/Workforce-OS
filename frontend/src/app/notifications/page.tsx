"use client";

import { useState } from "react";

type Category = "AI Suggestions" | "Approval" | "System";

interface Notification {
  id: string;
  title: string;
  category: Category;
  timeAgo: string;
  unread: boolean;
  actionLabel: string | null;
}

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

const INITIAL_NOTIFICATIONS: Notification[] = [
  { id: makeId(), title: "6 roles flagged for review by AI Suggestions", category: "AI Suggestions", timeAgo: "2 hours ago", unread: true, actionLabel: "Review" },
  { id: makeId(), title: "Obioma Chukwu submitted an annual leave request", category: "Approval", timeAgo: "3 hours ago", unread: true, actionLabel: "Review" },
  { id: makeId(), title: "Payroll run for August is pending approval", category: "System", timeAgo: "5 hours ago", unread: true, actionLabel: "View" },
  { id: makeId(), title: "Yusuf Ibrahim's sick leave was approved by HR", category: "Approval", timeAgo: "1 day ago", unread: false, actionLabel: null },
  { id: makeId(), title: "New performance review cycle has opened for Q4", category: "System", timeAgo: "1 day ago", unread: false, actionLabel: null },
  { id: makeId(), title: "Organization structure changes detected, new AI suggestions available", category: "AI Suggestions", timeAgo: "2 days ago", unread: false, actionLabel: "Review" },
  { id: makeId(), title: "Monthly attendance report for July is ready", category: "System", timeAgo: "3 days ago", unread: false, actionLabel: "View" },
  { id: makeId(), title: "Kemi Adebayo's leave adjustment request was approved", category: "Approval", timeAgo: "4 days ago", unread: false, actionLabel: null },
];

const FILTERS = ["All", "Unread", "Approvals", "AI Suggestions", "System"];

function iconClasses(category: Category) {
  if (category === "AI Suggestions") {
    return "bg-indigo-500/20 text-indigo-300";
  }
  if (category === "Approval") {
    return "bg-amber-500/20 text-amber-300";
  }
  return "bg-emerald-500/20 text-emerald-300";
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>(INITIAL_NOTIFICATIONS);
  const [activeFilter, setActiveFilter] = useState("All");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const unreadCount = notifications.filter(function (n: Notification) {
    return n.unread;
  }).length;

  function markAllRead() {
    setNotifications(
      notifications.map(function (n: Notification) {
        return { ...n, unread: false };
      })
    );
  }

  function selectNotification(id: string) {
    setSelectedId(id);
    setNotifications(
      notifications.map(function (n: Notification) {
        if (n.id === id) {
          return { ...n, unread: false };
        }
        return n;
      })
    );
  }

  const filtered = notifications.filter(function (n: Notification) {
    if (activeFilter === "All") {
      return true;
    }
    if (activeFilter === "Unread") {
      return n.unread;
    }
    if (activeFilter === "Approvals") {
      return n.category === "Approval";
    }
    return n.category === activeFilter;
  });

  const selected = notifications.find(function (n: Notification) {
    return n.id === selectedId;
  });

  return (
    <div className="min-h-screen w-full bg-[#05070f] px-8 py-8 text-white">
      <p className="text-xs text-gray-500">Dashboard &gt; Notifications</p>
      <div className="mt-1 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Notifications</h1>
          <span className="text-sm font-medium text-indigo-400">{unreadCount} unread</span>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map(function (filter) {
            const isActive = activeFilter === filter;
            const count = filter === "Unread" ? unreadCount : null;
            return (
              <button
                key={filter}
                type="button"
                onClick={function () {
                  setActiveFilter(filter);
                }}
                className={
                  "rounded-lg px-4 py-2 text-sm font-medium " +
                  (isActive ? "bg-indigo-500 text-white" : "bg-[#0d1220] text-gray-400 hover:bg-white/5")
                }
              >
                {filter}
                {count !== null ? " (" + count + ")" : ""}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={markAllRead}
          className="text-sm font-medium text-indigo-400 hover:text-indigo-300"
        >
          Mark all as read
        </button>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
        <div className="divide-y divide-white/5 rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
          {filtered.length === 0 ? (
            <div className="p-10 text-center text-sm text-gray-500">No notifications match this filter.</div>
          ) : (
            filtered.map(function (n: Notification) {
              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={function () {
                    selectNotification(n.id);
                  }}
                  className={
                    "flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-white/5 " +
                    (n.id === selectedId ? "bg-white/5" : "")
                  }
                >
                  {n.unread && <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-400" />}
                  <span
                    className={
                      "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold " +
                      iconClasses(n.category)
                    }
                  >
                    {n.category === "AI Suggestions" ? "AI" : n.category === "Approval" ? "A" : "S"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={"block text-sm " + (n.unread ? "font-semibold text-white" : "text-gray-300")}>
                      {n.title}
                    </span>
                    <span className="text-xs text-gray-500">{n.category}</span>
                  </span>
                  <span className="flex-shrink-0 text-xs text-gray-500">{n.timeAgo}</span>
                  {n.actionLabel && (
                    <span className="flex-shrink-0 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white">
                      {n.actionLabel}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>

        <div className="flex items-center justify-center rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
          {selected ? (
            <div className="text-center">
              <p className="text-sm text-gray-500">{selected.category}</p>
              <p className="mt-2 text-base font-semibold">{selected.title}</p>
              <p className="mt-1 text-xs text-gray-500">{selected.timeAgo}</p>
            </div>
          ) : (
            <div className="text-center">
              <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-gray-500">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  <line x1="2" y1="2" x2="22" y2="22" />
                </svg>
              </div>
              <p className="font-semibold">No notifications</p>
              <p className="mt-1 text-sm text-gray-500">
                You are all caught up. New notifications will appear here.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
