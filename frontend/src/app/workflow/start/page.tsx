"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface TemplateStep {
  title: string;
  department: string;
  turnaround: string;
}

interface TemplateOption {
  id: string;
  name: string;
  steps: TemplateStep[];
}

const TEMPLATE_OPTIONS: TemplateOption[] = [
  {
    id: "equipment-request",
    name: "Equipment Request",
    steps: [
      { title: "Submit request form", department: "Department A", turnaround: "1 Day" },
      { title: "Manager review and approval", department: "Department B", turnaround: "2 Days" },
      { title: "Process and fulfill request", department: "Department C", turnaround: "3 Days" },
    ],
  },
  {
    id: "leave-approval",
    name: "Leave Approval",
    steps: [
      { title: "Submit leave request", department: "HR", turnaround: "1 Day" },
      { title: "Manager approval", department: "Department B", turnaround: "1 Day" },
      { title: "HR confirmation", department: "HR", turnaround: "1 Day" },
    ],
  },
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

export default function StartWorkflowPage() {
  const router = useRouter();
  const [selectedTemplateId, setSelectedTemplateId] = useState(TEMPLATE_OPTIONS[0].id);
  const [caseName, setCaseName] = useState("");
  const [notes, setNotes] = useState("");

  const selectedTemplate = TEMPLATE_OPTIONS.find(function (t: TemplateOption) {
    return t.id === selectedTemplateId;
  });

  function handleStart() {
    if (!caseName.trim()) {
      window.alert("Please enter a case name before starting the workflow.");
      return;
    }
    // TODO: replace with a real call to the Workflow module endpoint
    // once the backend is ready.
    console.log("Workflow started:", { selectedTemplateId, caseName, notes });
    router.push("/workflow/tracker");
  }

  function handleCancel() {
    router.push("/workflow/templates");
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />
      <div className="flex-1 px-8 py-8">
        <p className="text-xs text-gray-500">Dashboard &gt; Workflow Templates &gt; Start Workflow</p>
        <h1 className="mt-1 text-2xl font-bold">Start Workflow</h1>

        <div className="mt-6 max-w-2xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6">
          <label className="mb-2 block text-sm font-medium text-gray-200">Select Template</label>
          <select
            value={selectedTemplateId}
            onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
              setSelectedTemplateId(e.target.value);
            }}
            className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500"
          >
            {TEMPLATE_OPTIONS.map(function (t: TemplateOption) {
              return (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              );
            })}
          </select>

          <p className="mb-2 mt-6 text-sm font-medium text-gray-200">Template Steps</p>
          <div className="space-y-3">
            {selectedTemplate &&
              selectedTemplate.steps.map(function (step: TemplateStep, index: number) {
                return (
                  <div key={step.title} className="flex items-center gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                    <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
                      {index + 1}
                    </span>
                    <div>
                      <p className="text-sm font-semibold">{step.title}</p>
                      <p className="text-xs text-gray-500">
                        <span className="rounded bg-white/10 px-1.5 py-0.5 text-indigo-300">{step.department}</span>
                        {"  "}Turnaround: {step.turnaround}
                      </p>
                    </div>
                  </div>
                );
              })}
          </div>

          <div className="mt-6">
            <label className="mb-2 block text-sm font-medium text-gray-200">
              Case Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={caseName}
              onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                setCaseName(e.target.value);
              }}
              placeholder="e.g. Enter a name or reference for this case"
              className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
          </div>

          <div className="mt-4">
            <label className="mb-2 block text-sm font-medium text-gray-200">Notes</label>
            <textarea
              rows={3}
              value={notes}
              onChange={function (e: React.ChangeEvent<HTMLTextAreaElement>) {
                setNotes(e.target.value);
              }}
              placeholder="Add any additional context or notes (optional)"
              className="w-full resize-none rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
          </div>

          <div className="mt-6 flex items-center justify-end gap-3 border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-white/15 px-5 py-2.5 text-sm font-medium text-white hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleStart}
              className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600"
            >
              Start Workflow
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
