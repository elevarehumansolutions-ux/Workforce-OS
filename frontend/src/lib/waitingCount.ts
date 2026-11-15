"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api";

// How much work is waiting for the signed-in person: the red number on "Tasks" in the menu.
// It is their open tasks (counted even if they have not clocked in) plus, for HR and department heads,
// the unassigned tasks they must hand out. One shared counter feeds every place that shows it, so the
// desktop menu and the phone menu do not each ask the server.

const REFRESH_EVERY_MS = 60000;

let latest = 0;
const listeners: ((count: number) => void)[] = [];
let timer: number | null = null;

function refresh() {
  apiFetch<{ total: number }>("/tasks/waiting-count", { method: "GET" })
    .then(function (result) {
      latest = result.total;
      for (const listener of listeners) listener(latest);
    })
    .catch(function () {
      // Offline or signed out: keep the number we have. The page itself reports real errors.
    });
}

function refreshIfVisible() {
  if (document.visibilityState === "visible") refresh();
}

// Call after something changes the number at once (a task handed out or completed).
export function refreshWaitingCount() {
  refresh();
}

// The current number. Starts the shared refresh when the first place uses it and stops it when the last leaves.
export function useWaitingCount(): number {
  const [count, setCount] = useState(latest);
  const pathname = usePathname();

  useEffect(function () {
    listeners.push(setCount);
    if (listeners.length === 1) {
      timer = window.setInterval(refreshIfVisible, REFRESH_EVERY_MS);
      document.addEventListener("visibilitychange", refreshIfVisible);
    }
    return function () {
      const index = listeners.indexOf(setCount);
      if (index !== -1) listeners.splice(index, 1);
      if (listeners.length === 0) {
        if (timer !== null) window.clearInterval(timer);
        timer = null;
        document.removeEventListener("visibilitychange", refreshIfVisible);
      }
    };
  }, []);

  // Moving to another page is a good moment to look again.
  useEffect(
    function () {
      refresh();
    },
    [pathname]
  );

  return count;
}
