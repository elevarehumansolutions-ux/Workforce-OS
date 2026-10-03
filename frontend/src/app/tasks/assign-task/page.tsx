"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
      <div className="flex items-center gap-3 border-t border-white/10 px-6 pt-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
          NA
        </div>
        <div>
          <p className="text-sm font-medium text-white">Ngozi Adeyemi</p>
          <p className="text-xs text-gray-500">Engineering Manager</p>
        </div>
      </div>
    </aside>
  );
}

type Priority = "Low" | "Medium" | "High";

interface AssignTaskFormData {
  assignTo: string;
  taskTitle: string;
  taskDescription: string;
  linkedKpi: string;
  dueDate: string;
  priority: Priority;
}

export default function AssignTaskPage() {
  const router = useRouter();
  const [formData, setFormData] = useState<AssignTaskFormData>({
    assignTo: "Adaeze Okonkwo",
    taskTitle: "Optimize database query indexing for metrics endpoint",
    taskDescription:
      "Investigate high response latency on the main telemetry load paths. Review existing indexes on performance metrics table and propose missing indexes to satisfy API SLAs.",
    linkedKpi: "Code Review Turnaround",
    dueDate: "2026-08-29",
    priority: "Medium",
  });

  function updateField(field: keyof AssignTaskFormData, value: string) {
    setFormData(function (prev) {
      return { ...prev, [field]: value };
    });
  }

  const PRIORITIES: Priority[] = ["Low", "Medium", "High"];

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Tasks")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <h1 className="text-xl font-bold text-white">Assign Task</h1>
            <p className="text-sm text-gray-500">Create and delegate action items to your engineering workforce</p>
          </div>
          <div className="flex items-center gap-4">
            <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">
                1
              </span>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">
              WOS MVP Ready
            </span>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="max-w-2xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
            <h2 className="text-base font-semibold text-white">Task Details</h2>
            <p className="mt-1 text-sm text-gray-500">Fill out the fields below to dispatch a new workforce assignment.</p>

            <div className="mt-6 space-y-5">
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                  Assign To *
                </label>
                <select
                  value={formData.assignTo}
                  onChange={(e) => updateField("assignTo", e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                >
                  <option>Adaeze Okonkwo</option>
                  <option>Tunde Balogun</option>
                  <option>Emeka Nwankwo</option>
                  <option>Amara Eze</option>
                </select>
                <p className="mt-1 text-xs text-gray-600">Engineering &bull; Software Engineer</p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                  Task Title *
                </label>
                <input
                  type="text"
                  value={formData.taskTitle}
                  onChange={(e) => updateField("taskTitle", e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                  Task Description
                </label>
                <textarea
                  rows={4}
                  value={formData.taskDescription}
                  onChange={(e) => updateField("taskDescription", e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                    Linked KPI
                  </label>
                  <select
                    value={formData.linkedKpi}
                    onChange={(e) => updateField("linkedKpi", e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                  >
                    <option>Code Review Turnaround</option>
                    <option>Deployment Frequency</option>
                    <option>Incident Response Time</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                    Due Date *
                  </label>
                  <input
                    type="date"
                    value={formData.dueDate}
                    onChange={(e) => updateField("dueDate", e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                  Task Priority *
                </label>
                <div className="flex gap-2">
                  {PRIORITIES.map(function (priority) {
                    const isActive = priority === formData.priority;
                    let dotClass = "h-2 w-2 rounded-full ";
                    if (priority === "Low") {
                      dotClass = dotClass + "bg-emerald-400";
                    } else if (priority === "Medium") {
                      dotClass = dotClass + "bg-amber-400";
                    } else {
                      dotClass = dotClass + "bg-red-400";
                    }
                    let btnClass = "flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition ";
                    if (isActive) {
                      btnClass = btnClass + "border-indigo-500 bg-indigo-500/15 text-white";
                    } else {
                      btnClass = btnClass + "border-white/10 text-gray-300 hover:bg-white/5";
                    }
                    return (
                      <button
                        key={priority}
                        type="button"
                        onClick={() => updateField("priority", priority)}
                        className={btnClass}
                      >
                        <span className={dotClass} />
                        {priority}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="mt-8 flex items-center justify-end gap-3 border-t border-white/10 pt-6">
              <button
                type="button"
                onClick={() => router.back()}
                className="rounded-lg border border-white/10 px-5 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => console.log("Assign task payload:", formData)}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600"
              >
                Assign Task
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

