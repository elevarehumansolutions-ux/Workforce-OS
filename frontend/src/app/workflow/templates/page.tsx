"use client";

import { useRouter } from "next/navigation";

interface Template {
  id: string;
  name: string;
  steps: number;
  lastEdited: string;
}

const TEMPLATES: Template[] = [
  { id: "onboarding-checklist", name: "Onboarding Checklist", steps: 4, lastEdited: "Aug 24, 2026" },
  { id: "equipment-request", name: "Equipment Request", steps: 3, lastEdited: "Jul 19, 2026" },
  { id: "leave-approval", name: "Leave Approval", steps: 5, lastEdited: "Jun 02, 2026" },
  { id: "expense-report", name: "Expense Report", steps: 6, lastEdited: "May 28, 2026" },
  { id: "document-review", name: "Document Review", steps: 3, lastEdited: "May 11, 2026" },
];

function SidebarNav() {
  const items = [
    "Dashboard",
    "Employees",
    "Attendance",
    "Leave Management",
    "Workflow",
    "Tasks",
    "Payroll",
    "Reports",
    "Settings",
  ];
  return (
    <div className="flex w-56 flex-shrink-0 flex-col border-r border-white/10 px-4 py-6">
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
        {items.map(function (item) {
          const isActive = item === "Workflow";
          return (
            <a
              key={item}
              href="#"
              className={
                "rounded-lg px-3 py-2.5 text-sm " +
                (isActive ? "bg-indigo-500 font-medium text-white" : "text-gray-400 hover:bg-white/5")
              }
            >
              {item}
            </a>
          );
        })}
      </nav>
    </div>
  );
}

export default function WorkflowTemplatesHubPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />
      <div className="flex-1 px-8 py-8">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Workflow Templates</p>
            <h1 className="mt-1 text-2xl font-bold">Workflow Templates</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={function () {
                router.push("/workflow/tracker");
              }}
              className="rounded-lg border border-indigo-500 px-4 py-2 text-sm font-medium text-indigo-400 hover:bg-indigo-500/10"
            >
              Active Tracker
            </button>
            <button
              type="button"
              onClick={function () {
                router.push("/workflow/start");
              }}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600"
            >
              + Start Workflow
            </button>
            <button
              type="button"
              onClick={function () {
                router.push("/workflow/new-template");
              }}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600"
            >
              + New Template
            </button>
          </div>
        </div>

        <div className="mt-6 overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80">
          <table className="w-full min-w-[600px] text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-5 py-3 font-medium">Template Name</th>
                <th className="px-5 py-3 font-medium">Steps</th>
                <th className="px-5 py-3 font-medium">Last Edited</th>
                <th className="px-5 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {TEMPLATES.map(function (t: Template) {
                return (
                  <tr key={t.id} className="border-b border-white/5">
                    <td className="px-5 py-4 font-medium">{t.name}</td>
                    <td className="px-5 py-4">
                      <span className="rounded bg-indigo-500/15 px-2 py-1 text-xs font-medium text-indigo-300">
                        {t.steps} Steps
                      </span>
                    </td>
                    <td className="px-5 py-4 text-gray-400">{t.lastEdited}</td>
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        onClick={function () {
                          router.push("/workflow/new-template");
                        }}
                        className="text-gray-500 hover:text-white"
                        aria-label="Edit template"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
