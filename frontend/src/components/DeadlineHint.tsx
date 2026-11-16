"use client";

import { useEffect, useState } from "react";
import { formatDuration } from "@/lib/tasks";

// A plain line under a deadline box that says how far away the chosen moment is, so changing the time of day
// but not the date (a deadline a day away that looks like minutes away) is easy to notice.
//   "That is in 3 minutes (Mon 16 Nov, 03:29 PM)"
//   "That is in 1 day (Tue 17 Nov, 03:29 PM)"
//   "That time has already passed (5 minutes ago)"
// `value` is what an <input type="datetime-local"> gives: "2026-11-16T15:29", or "" when nothing is chosen.
export default function DeadlineHint({ value }: { value: string }) {
  // "Now" is kept in state and refreshed every 30 seconds (reading the clock while rendering is not allowed).
  const [now, setNow] = useState(function () {
    return Date.now();
  });
  useEffect(function () {
    const timer = window.setInterval(function () {
      setNow(Date.now());
    }, 30000);
    return function () {
      window.clearInterval(timer);
    };
  }, []);

  if (!value) return null;
  const chosen = new Date(value);
  if (Number.isNaN(chosen.getTime())) return null;

  const seconds = Math.round((chosen.getTime() - now) / 1000);
  const when = chosen.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  if (seconds < 0) {
    return (
      <p className="mt-1 text-xs text-amber-300">
        That time has already passed ({formatDuration(-seconds)} ago, {when}).
      </p>
    );
  }
  if (seconds < 60) {
    return <p className="mt-1 text-xs text-gray-400">That is less than a minute away ({when}).</p>;
  }
  return (
    <p className="mt-1 text-xs text-gray-400">
      That is in {formatDuration(seconds)} ({when}).
    </p>
  );
}
