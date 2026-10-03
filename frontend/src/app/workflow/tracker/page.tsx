"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

type CaseStatus = "On Time" | "Overdue";

interface WorkflowCase {
  id: string;
  caseName: string;
  template: string;
  currentStep: string;
  handler: string;
  status: CaseStatus;
  started: string;
  completed: boolean;
}

const CASES: WorkflowCase[] = [
  { id: "CASE-001", caseName: "CASE-001", template: "Onboarding Checklist", currentStep: "Step 2 of 4, Review documentation", handler: "Aisha D.", status: "On Time", started: "Aug 28, 2026", completed: false },
  { id: "CASE-002", caseName: "CASE-002", template: "Equipment Request", currentStep: "Step 2 of 3, Manager review and approval", handler: "Tolu B.", status: "Overdue", started: "Aug 25, 2026", completed: false },
  { id: "CASE-003", caseName: "CASE-003", template: "Leave Approval", currentStep: "Step 3 of 5, Department head sign-off", handler: "Funke M.", status: "On Time", started: "Aug 30, 2026", completed: false },
  { id: "CASE-004", caseName: "CASE-004", template: "Document Review", currentStep: "Step 1 of 3, Submit request form", handler: "Bola K.", status: "On Time", started: "Sep 01, 2026", completed: false },
  { id: "CASE-005", caseName: "CASE-005", template: "Expense Report", currentStep: "Step 4 of 6, Finance verification", handler: "Chidi O.", status: "Overdue", started: "Aug 20, 2026", completed: false },
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

export default function WorkflowTrackerPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"active" | "completed">("active");
  const [search, setSearch] = useState("");
  const [templateFilter, setTemplateFilter] = useState("All");

  const templateOptions = ["All"].concat(
    Array.from(
      new Set(
        CASES.map(function (c: WorkflowCase) {
          return c.template;
        })
      )
    )
  );

  const filtered = CASES.filter(function (c: WorkflowCase) {
    const matchesTab = tab === "active" ? !c.completed : c.completed;
    const matchesSearch = c.caseName.toLowerCase().includes(search.toLowerCase());
    const matchesTemplate = templateFilter === "All" || c.template === templateFilter;
    return matchesTab && matchesSearch && matchesTemplate;
  });

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />
      <div className="flex-1 px-8 py-8">
        <p className="text-xs text-gray-500">Dashboard &gt; Workflow Templates &gt; Tracker</p>
        <h1 className="mt-1 text-2xl font-bold">Workflow Tracker</h1>
        <p className="mt-1 text-sm text-gray-500">Track active workflow cases and their progress</p>

        <div className="mt-6 flex gap-6 border-b border-white/10">
          <button
            type="button"
            onClick={function () {
              setTab("active");
            }}
            className={
              "border-b-2 pb-3 text-sm font-medium " +
              (tab === "active" ? "border-indigo-500 text-white" : "border-transparent text-gray-500")
            }
          >
            Active Workflows
          </button>
          <button
            type="button"
            onClick={function () {
              setTab("completed");
            }}
            className={
              "border-b-2 pb-3 text-sm font-medium " +
              (tab === "completed" ? "border-indigo-500 text-white" : "border-transparent text-gray-500")
            }
          >
            Completed
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              value={search}
              onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                setSearch(e.target.value);
              }}
              placeholder="Search cases..."
              className="rounded-lg border border-white/10 bg-[#0d1220] px-4 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
            <select
              value={templateFilter}
              onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                setTemplateFilter(e.target.value);
              }}
              className="rounded-lg border border-white/10 bg-[#0d1220] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
            >
              {templateOptions.map(function (opt) {
                return (
                  <option key={opt} value={opt}>
                    Template: {opt}
                  </option>
                );
              })}
            </select>
          </div>
          <button
            type="button"
            className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
          >
            Export CSV
          </button>
        </div>

        <div className="mt-4 overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-5 py-3 font-medium">Case Name</th>
                <th className="px-5 py-3 font-medium">Template</th>
                <th className="px-5 py-3 font-medium">Current Step</th>
                <th className="px-5 py-3 font-medium">Handler</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-gray-500">
                    No cases match your filters.
                  </td>
                </tr>
              ) : (
                filtered.map(function (c: WorkflowCase) {
                  return (
                    <tr
                      key={c.id}
                      onClick={function () {
                        router.push("/workflow/case-detail");
                      }}
                      className="cursor-pointer border-b border-white/5 hover:bg-white/5"
                    >
                      <td className="px-5 py-4 font-semibold">{c.caseName}</td>
                      <td className="px-5 py-4 text-gray-300">{c.template}</td>
                      <td className="px-5 py-4 text-gray-500">{c.currentStep}</td>
                      <td className="px-5 py-4 text-gray-300">{c.handler}</td>
                      <td className="px-5 py-4">
                        <span
                          className={
                            "rounded-full px-3 py-1 text-xs font-medium " +
                            (c.status === "Overdue"
                              ? "bg-red-500/15 text-red-400"
                              : "bg-emerald-500/15 text-emerald-400")
                          }
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-gray-500">{c.started}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-gray-500">Showing 1-{filtered.length} of {filtered.length} records</p>
      </div>
    </div>
  );
}
