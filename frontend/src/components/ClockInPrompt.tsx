"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Modal from "@/components/Modal";
import { apiFetch, getAccessToken } from "@/lib/api";
import { errorMessage } from "@/lib/tasks";
import type { PaginatedResponse } from "@/lib/tasks";
import { dayInTimezone, fetchWorkingHours, isWorkingTime } from "@/lib/workingHours";

interface AttendanceRow {
  clock_in_at: string;
}

// Pages where the prompt never appears: signed-out pages, the company chooser, and the Attendance page
// itself (it already has the button).
const NO_PROMPT_PAGES = ["/", "/login", "/signup", "/forgot-password", "/reset-password", "/verify-email", "/accept-invite", "/organizations", "/attendance"];

// How long a check that found nothing to ask is trusted, so moving between pages does not repeat it.
const QUIET_FOR_MS = 10 * 60 * 1000;

// Kept while the tab is open: who has been asked on which day (so "Not now" is respected and the window
// does not come back on every page), and who need not be checked again for a while.
let askedKey = "";
let quietWho = "";
let quietUntil = 0;

// The signed-in person's id, read from the sign-in token. Used only to tell two people apart on a shared computer.
function personInToken(): string {
  const token = getAccessToken();
  if (!token) return "";
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const parsed = JSON.parse(window.atob(payload));
    return typeof parsed.sub === "string" ? parsed.sub : "";
  } catch {
    return "";
  }
}

function greetingNow(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

// Right after signing in, asks an employee who has not clocked in today to do it, with one button.
// Only on a working day inside the company's working hours. It is a question, not a gate: "Not now"
// closes it, and people without an employee record (an executive, for example) are never asked.
export default function ClockInPrompt() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [greeting, setGreeting] = useState("");
  const [asking, setAsking] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(
    function () {
      if (NO_PROMPT_PAGES.indexOf(pathname) !== -1 || pathname.indexOf("/onboarding") === 0) return;
      const who = personInToken();
      if (!who) return;
      if (quietWho === who && Date.now() < quietUntil) return;

      let cancelled = false;
      function stayQuiet() {
        quietWho = who;
        quietUntil = Date.now() + QUIET_FOR_MS;
      }

      Promise.all([apiFetch<PaginatedResponse<AttendanceRow>>("/attendance?limit=1", { method: "GET" }), fetchWorkingHours()])
        .then(function (results) {
          if (cancelled) return;
          const history = results[0];
          const week = results[1];
          const now = new Date();
          const today = dayInTimezone(week.timezone, now);
          const key = who + "|" + today;
          if (askedKey === key) return;

          // Already clocked in today (even if clocked out since): never ask again.
          if (history.data.length > 0 && dayInTimezone(week.timezone, new Date(history.data[0].clock_in_at)) === today) {
            askedKey = key;
            return;
          }
          if (!isWorkingTime(week, now)) {
            stayQuiet();
            return;
          }
          setGreeting(greetingNow());
          setAsking(key);
          setError("");
          setDone(false);
          setOpen(true);
        })
        .catch(function () {
          // No employee record (409), offline, or not allowed: nothing to ask, and no need to retry on every page.
          if (!cancelled) stayQuiet();
        });

      return function () {
        cancelled = true;
      };
    },
    [pathname]
  );

  function notNow() {
    // Remember the answer for today so it does not come back on the next page.
    askedKey = asking;
    setOpen(false);
  }

  async function clockIn() {
    setBusy(true);
    setError("");
    try {
      await apiFetch("/attendance/clock-in", { method: "POST" });
      askedKey = asking;
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, "Couldn't clock you in. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <Modal title={done ? "You're clocked in" : "Clock in to start your day"} onClose={busy ? function () {} : notNow}>
      {done ? (
        <div>
          <p className="text-sm text-gray-300">Your day has started. Your tasks are ready to open.</p>
          <div className="mt-5 flex justify-end">
            <button
              type="button"
              onClick={function () {
                setOpen(false);
              }}
              className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600"
            >
              Done
            </button>
          </div>
        </div>
      ) : (
        <div>
          <p className="text-sm text-gray-300">
            {greeting}. You haven&apos;t clocked in yet today. Your tasks only show up once you are clocked in.
          </p>
          {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
          <div className="mt-5 flex items-center justify-end gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={notNow}
              className="rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-white/5 disabled:opacity-50"
            >
              Not now
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={clockIn}
              className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Clocking in…" : "Clock in"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
