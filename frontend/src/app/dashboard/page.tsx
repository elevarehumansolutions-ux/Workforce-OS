"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Priority = "High" | "Medium" | "Low";

interface Task {
  id: string;
  title: string;
  priority: Priority;
  done: boolean;
}

const PRIORITY_ORDER: Record<Priority, number> = {
  High: 0,
  Medium: 1,
  Low: 2,
};

function priorityClasses(priority: Priority) {
  if (priority === "High") {
    return "bg-red-500/15 text-red-400";
  }
  if (priority === "Medium") {
    return "bg-amber-500/15 text-amber-400";
  }
  return "bg-white/10 text-gray-400";
}

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

const INITIAL_TASKS: Task[] = [
  { id: makeId(), title: "Complete Q3 performance review", priority: "High", done: false },
  { id: makeId(), title: "Submit weekly status report", priority: "High", done: false },
  { id: makeId(), title: "Update project documentation", priority: "Medium", done: true },
  { id: makeId(), title: "Review team meeting notes", priority: "Low", done: false },
];

export default function DashboardPage() {
  const router = useRouter();
  const [isClockedIn, setIsClockedIn] = useState(false);
  const [clockedInAt, setClockedInAt] = useState("");
  const [tasks, setTasks] = useState<Task[]>(INITIAL_TASKS);

  function handleClockToggle() {
    if (isClockedIn) {
      setIsClockedIn(false);
      setClockedInAt("");
    } else {
      setIsClockedIn(true);
      const now = new Date();
      setClockedInAt(
        now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) + " today"
      );
    }
  }

  function toggleTask(id: string) {
    setTasks(
      tasks.map(function (task: Task) {
        if (task.id === id) {
          return { ...task, done: !task.done };
        }
        return task;
      })
    );
  }

  const sortedTasks = [...tasks].sort(function (a: Task, b: Task) {
    return PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
  });

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <div className="flex w-60 flex-shrink-0 flex-col border-r border-white/10 px-4 py-6">
        <div className="mb-8 flex items-center gap-3 px-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
              <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
            </svg>
          </div>
          <span className="text-base font-bold">Elevare</span>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          <a href="#" className="flex items-center gap-3 rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-medium text-white">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
              <rect x="14" y="14" width="7" height="7" rx="1" />
            </svg>
            Dashboard
          </a>
          <a href="#" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-gray-400 hover:bg-white/5">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" />
              <path d="M8 2v4M16 2v4M3 10h18" />
            </svg>
            My Leave
          </a>
          <a href="#" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-gray-400 hover:bg-white/5">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3v18h18M7 15l4-4 3 3 5-6" />
            </svg>
            My KPIs
          </a>
        </nav>

        <div className="flex items-center gap-3 border-t border-white/10 pt-4">
          <div className="h-9 w-9 rounded-full bg-white/10" />
          <div>
            <p className="text-sm font-medium">Chukwuma Obi</p>
            <p className="text-xs text-gray-500">Software Engineer</p>
          </div>
        </div>
      </div>

      <div className="flex-1 px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Good morning, Chukwuma</h1>
            <p className="text-sm text-gray-500">Wednesday, August 20, 2026</p>
          </div>
          <button
            type="button"
            onClick={function () {
              router.push("/notifications");
            }}
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#0d1220] text-gray-300 hover:bg-white/5"
            aria-label="Notifications"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </button>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Attendance Shift OS</h2>
              <span className="text-xs text-gray-500">GMT +1 (Lagos)</span>
            </div>
            <p className="mt-4 text-sm text-gray-500">Current Status</p>
            <div className="mt-1 flex items-center gap-2">
              <span className={"h-2 w-2 rounded-full " + (isClockedIn ? "bg-emerald-400" : "bg-red-500")} />
              <span className="text-lg font-semibold">{isClockedIn ? "Clocked In" : "Not Clocked In"}</span>
            </div>
            <button
              type="button"
              onClick={handleClockToggle}
              className={
                "mt-4 w-full rounded-lg py-3 text-sm font-semibold text-white transition " +
                (isClockedIn ? "bg-red-500 hover:bg-red-600" : "bg-indigo-500 hover:bg-indigo-600")
              }
            >
              {isClockedIn ? "Clock Out" : "Clock In"}
            </button>
            <p className="mt-2 text-center text-xs text-gray-500">
              {isClockedIn ? "Clocked in at " + clockedInAt : "Last clock-out: Yesterday at 5:04 PM"}
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h2 className="text-base font-semibold">Today&apos;s Tasks</h2>
            {!isClockedIn ? (
              <div className="mt-8 flex flex-col items-center justify-center py-8 text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-white/15 text-gray-500">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M12 7v5l3 3" />
                  </svg>
                </div>
                <p className="font-medium text-gray-400">Clock in to see today&apos;s tasks</p>
                <p className="mt-1 text-xs text-gray-600">
                  Your task list will appear once you are on the clock
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                {sortedTasks.map(function (task: Task) {
                  return (
                    <div key={task.id} className="flex items-center justify-between gap-3">
                      <label className="flex flex-1 items-center gap-3 text-sm">
                        <input
                          type="checkbox"
                          checked={task.done}
                          onChange={function () {
                            toggleTask(task.id);
                          }}
                          className="h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500"
                        />
                        <span className={task.done ? "text-gray-500 line-through" : "text-gray-200"}>
                          {task.title}
                        </span>
                      </label>
                      <span className={"rounded px-2 py-0.5 text-xs font-medium " + priorityClasses(task.priority)}>
                        {task.priority}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h2 className="text-base font-semibold">My KPIs (Q3 Cycle)</h2>
            <div className="mt-4 space-y-4">
              {[
                { label: "Customer Satisfaction", value: 87, display: "87 / 100" },
                { label: "Project Delivery Rate", value: 92, display: "92% / 100%" },
                { label: "Code Review Turnaround", value: 70, display: "4.2h / 6h max" },
              ].map(function (kpi) {
                return (
                  <div key={kpi.label}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-300">{kpi.label}</span>
                      <span className="font-semibold">{kpi.display}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{ width: kpi.value + "%" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h2 className="text-base font-semibold">My Leave Balance</h2>
            <div className="mt-4 grid grid-cols-3 gap-3">
              {[
                { label: "Annual", used: 15, total: 21 },
                { label: "Sick", used: 8, total: 10 },
                { label: "Personal", used: 3, total: 5 },
              ].map(function (leave) {
                return (
                  <div key={leave.label} className="rounded-lg border border-white/10 bg-[#0a0e1a] p-3">
                    <p className="text-xs font-medium text-gray-300">{leave.label}</p>
                    <p className="mt-1 text-sm font-semibold">
                      {leave.used} / {leave.total} days
                    </p>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full bg-emerald-500"
                        style={{ width: (leave.used / leave.total) * 100 + "%" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-6">
          <h2 className="mb-3 text-base font-semibold">Quick Actions</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <button
              type="button"
              className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0d1220]/80 px-4 py-4 text-left hover:bg-white/5"
            >
              <span className="flex items-center gap-3 text-sm font-medium">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" />
                  <path d="M8 2v4M16 2v4M3 10h18" />
                </svg>
                Submit Leave Request
              </span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
            <button
              type="button"
              className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0d1220]/80 px-4 py-4 text-left hover:bg-white/5"
            >
              <span className="flex items-center gap-3 text-sm font-medium">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 20V10M18 20V4M6 20v-4" />
                </svg>
                View Attendance History
              </span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}