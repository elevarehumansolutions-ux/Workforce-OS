"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface Step {
  id: string;
  description: string;
  department: string;
  turnaroundDays: number;
  handler: string;
}

const DEPARTMENT_OPTIONS = ["Department A", "Department B", "Department C", "HR", "Finance", "Engineering"];

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

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

export default function TemplateBuilderPage() {
  const router = useRouter();
  const [templateName, setTemplateName] = useState("");
  const [steps, setSteps] = useState<Step[]>([
    { id: makeId(), description: "", department: "", turnaroundDays: 0, handler: "" },
  ]);

  function updateStep(id: string, field: keyof Step, value: string | number) {
    setSteps(
      steps.map(function (s: Step) {
        if (s.id === id) {
          return { ...s, [field]: value };
        }
        return s;
      })
    );
  }

  function addStep() {
    setSteps([...steps, { id: makeId(), description: "", department: "", turnaroundDays: 0, handler: "" }]);
  }

  function removeStep(id: string) {
    setSteps(
      steps.filter(function (s: Step) {
        return s.id !== id;
      })
    );
  }

  function handleSave() {
    // TODO: replace with a real call to the Workflow module endpoint
    // once the backend is ready.
    console.log("Template saved:", { templateName, steps });
    router.push("/workflow/templates");
  }

  function handleCancel() {
    router.push("/workflow/templates");
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />
      <div className="flex-1 px-8 py-8">
        <p className="text-xs text-gray-500">Dashboard &gt; Workflow Templates &gt; Template Builder</p>
        <h1 className="mt-1 text-2xl font-bold">Template Builder</h1>

        <div className="mt-6 max-w-3xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6">
          <label className="mb-2 block text-sm font-medium text-gray-200">
            Template Name <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={templateName}
            onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
              setTemplateName(e.target.value);
            }}
            placeholder="e.g. Enter template name"
            className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
          />

          <h2 className="mt-6 text-sm font-semibold text-gray-200">Steps</h2>
          <div className="mt-3 space-y-4">
            {steps.map(function (step: Step, index: number) {
              return (
                <div key={step.id} className="rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-1 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
                      {index + 1}
                    </span>
                    <div className="flex-1 space-y-3">
                      <div>
                        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">
                          Step Description <span className="text-red-400">*</span>
                        </label>
                        <input
                          type="text"
                          value={step.description}
                          onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                            updateStep(step.id, "description", e.target.value);
                          }}
                          placeholder="e.g. Describe what happens at this step"
                          className="w-full rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                        />
                      </div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                        <div>
                          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">
                            Department <span className="text-red-400">*</span>
                          </label>
                          <select
                            value={step.department}
                            onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                              updateStep(step.id, "department", e.target.value);
                            }}
                            className="w-full rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
                          >
                            <option value="">Select department</option>
                            {DEPARTMENT_OPTIONS.map(function (dept) {
                              return (
                                <option key={dept} value={dept}>
                                  {dept}
                                </option>
                              );
                            })}
                          </select>
                        </div>
                        <div>
                          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">
                            Default Turnaround Time
                          </label>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              value={step.turnaroundDays}
                              onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                                updateStep(step.id, "turnaroundDays", Number(e.target.value));
                              }}
                              className="w-full rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
                            />
                            <span className="flex items-center px-2 text-xs text-gray-500">Days</span>
                          </div>
                        </div>
                        <div>
                          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">
                            Default Handler
                          </label>
                          <input
                            type="text"
                            value={step.handler}
                            onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                              updateStep(step.id, "handler", e.target.value);
                            }}
                            placeholder="Select handler (optional)"
                            className="w-full rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                          />
                        </div>
                      </div>
                    </div>
                    {steps.length > 1 && (
                      <button
                        type="button"
                        onClick={function () {
                          removeStep(step.id);
                        }}
                        className="mt-1 flex-shrink-0 text-gray-500 hover:text-red-400"
                        aria-label="Remove step"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 6 6 18M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <button
            type="button"
            onClick={addStep}
            className="mt-4 rounded-lg border border-dashed border-indigo-500/40 px-4 py-2 text-sm font-medium text-indigo-400 hover:border-indigo-500/70"
          >
            + Add Step
          </button>

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
              onClick={handleSave}
              className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600"
            >
              Save Template
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
