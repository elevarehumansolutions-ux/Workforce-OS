"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

// How often the number is refreshed while the page is open and visible.
const REFRESH_EVERY_MS = 60000;

// Other code (the Notifications page) fires this when it marks something read, so the number drops at once.
export const NOTIFICATIONS_CHANGED = "notifications-changed";

// A bell in the top bar with the number of unread notifications; clicking it opens the Notifications page.
export default function NotificationBell() {
  const [unread, setUnread] = useState(0);

  useEffect(function () {
    let stopped = false;

    function refresh() {
      apiFetch<{ unread: number }>("/notifications/unread-count", { method: "GET" })
        .then(function (result) {
          if (!stopped) setUnread(result.unread);
        })
        .catch(function () {
          // Offline or signed out: keep the number we have. The page itself reports real errors.
        });
    }

    function refreshIfVisible() {
      if (document.visibilityState === "visible") refresh();
    }

    refresh();
    const timer = window.setInterval(refreshIfVisible, REFRESH_EVERY_MS);
    document.addEventListener("visibilitychange", refreshIfVisible);
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh);
    return function () {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshIfVisible);
      window.removeEventListener(NOTIFICATIONS_CHANGED, refresh);
    };
  }, []);

  const label = unread > 99 ? "99+" : String(unread);

  return (
    <Link
      href="/notifications"
      aria-label={unread > 0 ? "Notifications, " + unread + " unread" : "Notifications"}
      title="Notifications"
      className="relative flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-gray-300 hover:bg-white/5 hover:text-white"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {unread > 0 ? (
        <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-semibold text-white">
          {label}
        </span>
      ) : null}
    </Link>
  );
}
