﻿"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";

interface MeResponse {
  user: { account_status: string };
}

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
  { label: "Attendance", href: "/attendance" },
  { label: "Leave Management", href: "/leave" },
  { label: "Workflow", href: "/workflow/templates" },
  { label: "Tasks", href: "/tasks" },
  { label: "Payroll", href: "/payroll" },
  { label: "Reports", href: "/reports" },
  { label: "Settings", href: "/settings" },
];

function SidebarNav(activeLabel: string) {
  return (
    <nav className="flex flex-col gap-1 px-3">
      {SIDEBAR_ITEMS.map(function (item) {
        const isActive = item.label === activeLabel;
        let linkClass = "rounded-lg px-3 py-2.5 text-sm transition ";
        if (isActive) {
          linkClass = linkClass + "bg-indigo-500/15 text-indigo-300 font-medium";
        } else {
          linkClass = linkClass + "text-gray-400 hover:bg-white/5 hover:text-gray-200";
        }
        return (
          <a key={item.label} href={item.href} className={linkClass}>
            {item.label}
          </a>
        );
      })}
    </nav>
  );
}

function SidebarShell(activeLabel: string) {
  return (
    <aside className="hidden w-64 flex-col justify-between border-r border-white/10 bg-[#0a0e1a] py-6 lg:flex">
      <div>
        <div className="mb-8 flex items-center gap-3 px-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500">
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
              <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
            </svg>
          </div>
          <span className="text-base font-bold text-white">Elevare</span>
        </div>
        {SidebarNav(activeLabel)}
      </div>
      <a
        href="/organizations"
        className="flex items-center gap-3 border-t border-white/10 px-6 pt-4 transition hover:bg-white/5"
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
          NA
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-white">Ngozi Adeyemi</p>
          <p className="text-xs text-gray-500">Engineering Manager</p>
        </div>
        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="text-gray-500">
          <path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </a>
    </aside>
  );
}

interface ActiveWorker {
  id: string;
  initials: string;
  name: string;
  timeRange: string;
  shift: string;
}

const ACTIVE_WORKERS: ActiveWorker[] = [
  { id: "1", initials: "AE", name: "Amara Eze", timeRange: "09:00 AM - 05:00 PM", shift: "Morning" },
  { id: "2", initials: "TB", name: "Tunde Balogun", timeRange: "02:00 PM - 10:00 PM", shift: "Mid-Day" },
  { id: "3", initials: "FA", name: "Fatima Abubakar", timeRange: "10:00 PM - 06:00 AM", shift: "Night Shift" },
  { id: "4", initials: "EN", name: "Emeka Nwankwo", timeRange: "09:00 AM - 05:00 PM", shift: "Morning" },
];

interface ApprovalRequest {
  id: string;
  name: string;
  detail: string;
}

const APPROVALS: ApprovalRequest[] = [
  { id: "1", name: "Obioma Chukwu", detail: "Annual Leave \u2022 Aug 25 - 29" },
  { id: "2", name: "Yusuf Ibrahim", detail: "Sick Leave \u2022 Aug 21" },
  { id: "3", name: "Kemi Adebayo", detail: "Shift Swap Request \u2022 Next Thursday" },
];

interface ActivityEntry {
  id: string;
  time: string;
  text: string;
}

const ACTIVITY: ActivityEntry[] = [
  { id: "1", time: "09:12 AM", text: "Chukwuma Obi submitted an annual leave request" },
  { id: "2", time: "09:05 AM", text: "Tunde Balogun clocked in (On-time)" },
  { id: "3", time: "08:55 AM", text: "Amara Eze clocked in (On-time)" },
  { id: "4", time: "08:30 AM", text: "Shift roster updated for upcoming cycle" },
  { id: "5", time: "08:15 AM", text: "Femi Alao request pending manager review" },
];

export default function ManagerDashboardPage() {
  const router = useRouter();
  // Starts true on both the server and client's first render (see the
  // Business DNA / verify-email fixes for why this can't read anything
  // client-only here) and only flips once the checks below clear, so the
  // dashboard never flashes before we know onboarding is actually done.
  const [checking, setChecking] = useState(true);

  useEffect(function () {
    let cancelled = false;
    async function guard() {
      if (!getAccessToken()) {
        router.replace("/login");
        return;
      }
      try {
        const me = await apiFetch<MeResponse>("/me", { method: "GET" });
        if (cancelled) return;
        if (me.user.account_status !== "verified") {
          router.replace("/verify-email");
          return;
        }
      } catch {
        // If /me itself fails, don't block the dashboard on it — apiFetch
        // already sends the person to /login on an unrecoverable 401.
        if (!cancelled) setChecking(false);
        return;
      }

      try {
        // There's no dedicated "onboarding_complete" flag on the API yet —
        // GET /business-dna 404ing is the most honest signal available
        // that the wizard was never finished (it's the first step, and
        // PUT /business-dna is what creates the profile). Worth asking
        // Emmanuel for a real flag if this ever gets more steps to check.
        await apiFetch("/business-dna", { method: "GET" });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace("/onboarding/business-dna");
          return;
        }
        // Any other failure (network blip, etc.): fail open rather than
        // trap the person on a loading screen.
      }

      if (!cancelled) setChecking(false);
    }
    guard();
    return function () {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (checking) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#05070f] text-white">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Dashboard")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <h1 className="text-xl font-bold text-white">Manager Dashboard</h1>
            <p className="text-sm text-gray-500">Corporate Operations &amp; Engineering Oversight</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => router.push("/workflow/start")}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              + Start Workflow
            </button>
            <button
              type="button"
              onClick={() => router.push("/tasks/assign-task")}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              + Assign Task
            </button>
            <button
              type="button"
              onClick={() => router.push("/employees/invite")}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              + Invite Employee
            </button>
            <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">1</span>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">WOS MVP Ready</span>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Team Attendance</p>
              <p className="mt-2 text-2xl font-bold text-white">94.2%</p>
              <span className="mt-1 inline-block text-xs font-medium text-emerald-400">&uarr; +2.4%</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Active Employees</p>
              <p className="mt-2 text-2xl font-bold text-white">47</p>
              <span className="mt-1 inline-block text-xs font-medium text-gray-500">Stable</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Pending Approvals</p>
              <p className="mt-2 text-2xl font-bold text-white">8</p>
              <span className="mt-1 inline-block text-xs font-medium text-amber-400">Action Required</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Avg KPI Score</p>
              <p className="mt-2 text-2xl font-bold text-white">78%</p>
              <span className="mt-1 inline-block text-xs font-medium text-emerald-400">&uarr; +5.1%</span>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold text-white">Today&apos;s Attendance Overview</h3>
              <div className="mt-4 flex items-center gap-4 text-sm text-gray-300">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Present: 42</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-400" /> Late: 3</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-400" /> Absent: 2</span>
              </div>
              <div className="mt-4 flex h-2 w-full overflow-hidden rounded-full bg-white/10">
                <div className="h-full bg-emerald-400" style={{ width: "89%" }} />
                <div className="h-full bg-amber-400" style={{ width: "6%" }} />
                <div className="h-full bg-red-400" style={{ width: "5%" }} />
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold text-white">Today&apos;s Active Workday</h3>
              <div className="mt-4 flex flex-col divide-y divide-white/5">
                {ACTIVE_WORKERS.map(function (worker) {
                  return (
                    <div key={worker.id} className="flex items-center justify-between py-2.5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                          {worker.initials}
                        </div>
                        <span className="text-sm font-medium text-white">{worker.name}</span>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-gray-400">{worker.timeRange}</p>
                        <p className="text-xs text-gray-600">{worker.shift}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold text-white">Pending Team Approvals</h3>
              <div className="mt-4 flex flex-col divide-y divide-white/5">
                {APPROVALS.map(function (approval) {
                  return (
                    <div key={approval.id} className="flex items-center justify-between py-3">
                      <div>
                        <p className="text-sm font-medium text-white">{approval.name}</p>
                        <p className="text-xs text-gray-500">{approval.detail}</p>
                      </div>
                      <div className="flex gap-2">
                        <button type="button" className="rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-medium text-red-300 transition hover:bg-red-500/25">
                          Reject
                        </button>
                        <button type="button" className="rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-600">
                          Approve
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold text-white">Recent Workforce Activity</h3>
              <div className="mt-4 flex flex-col gap-3">
                {ACTIVITY.map(function (entry) {
                  return (
                    <div key={entry.id} className="flex items-start gap-3 text-sm">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                      <span className="w-16 shrink-0 text-xs text-gray-600">{entry.time}</span>
                      <span className="text-gray-300">{entry.text}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

