"use client";

import { useRouter } from "next/navigation";

type StepState = "done" | "current" | "upcoming";

interface CaseStep {
  id: string;
  title: string;
  department: string;
  state: StepState;
  completedBy?: string;
  completedOn?: string;
  assignedTo?: string;
  deadline?: string;
  isOverdue?: boolean;
}

const CASE_STEPS: CaseStep[] = [
  {
    id: "1",
    title: "Step 1: Submit request form",
    department: "Department A",
    state: "done",
    completedBy: "Ngozi A.",
    completedOn: "Aug 25, 2026",
  },
  {
    id: "2",
    title: "Step 2: Manager review and approval",
    department: "Department B",
    state: "current",
    assignedTo: "Tolu B.",
    deadline: "Aug 27, 2026",
    isOverdue: true,
  },
  {
    id: "3",
    title: "Step 3: Process and fulfill request",
    department: "Department C",
    state: "upcoming",
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

export default function WorkflowCaseDetailPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />
      <div className="flex-1 px-8 py-8">
        <p className="text-xs text-gray-500">Dashboard &gt; Workflow Templates &gt; Tracker &gt; CASE-002</p>
        <h1 className="mt-1 text-2xl font-bold">CASE-002</h1>
        <p className="mt-1 text-sm text-gray-500">Template: Equipment Request &middot; Started: Aug 25, 2026</p>

        <div className="mt-6 max-w-3xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6">
          <h2 className="text-base font-semibold">Workflow Progress</h2>

          <div className="mt-4 space-y-0">
            {CASE_STEPS.map(function (step: CaseStep, index: number) {
              const isLast = index === CASE_STEPS.length - 1;
              return (
                <div key={step.id} className="relative flex gap-4 pb-8">
                  {!isLast && (
                    <span
                      className={
                        "absolute left-[15px] top-8 h-full w-0.5 " +
                        (step.state === "done" ? "bg-emerald-500" : "bg-white/10")
                      }
                    />
                  )}
                  <span
                    className={
                      "z-10 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold " +
                      (step.state === "done"
                        ? "bg-emerald-500/20 text-emerald-400"
                        : step.state === "current"
                        ? "border-2 border-indigo-500 bg-[#0d1220] text-indigo-400"
                        : "bg-white/5 text-gray-600")
                    }
                  >
                    {step.state === "done" ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    ) : (
                      index + 1
                    )}
                  </span>
                  <div
                    className={
                      "flex-1 rounded-lg p-3 " +
                      (step.state === "current" ? "border border-indigo-500/40 bg-indigo-500/5" : "")
                    }
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p
                        className={
                          "text-sm font-semibold " + (step.state === "upcoming" ? "text-gray-500" : "text-white")
                        }
                      >
                        {step.title}{" "}
                        <span className="ml-1 rounded bg-white/10 px-1.5 py-0.5 text-xs font-normal text-gray-400">
                          {step.department}
                        </span>
                      </p>
                      {step.isOverdue && (
                        <span className="rounded-full bg-red-500/15 px-3 py-1 text-xs font-medium text-red-400">
                          Overdue
                        </span>
                      )}
                    </div>
                    {step.state === "done" && (
                      <p className="mt-1 text-xs text-gray-500">
                        Completed by {step.completedBy} on {step.completedOn}
                      </p>
                    )}
                    {step.state === "current" && (
                      <p className="mt-1 flex items-center gap-3 text-xs text-gray-400">
                        <span>Assigned to: {step.assignedTo}</span>
                        <span className="flex items-center gap-1 text-red-400">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="9" />
                            <path d="M12 7v5l3 3" />
                          </svg>
                          Deadline: {step.deadline}
                        </span>
                      </p>
                    )}
                    {step.state === "upcoming" && (
                      <p className="mt-1 text-xs text-gray-600">Pending previous steps</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="border-t border-white/10 pt-4">
            <h3 className="text-sm font-semibold">Case Notes</h3>
            <p className="mt-1 text-sm text-gray-500">No notes added.</p>
          </div>
        </div>

        <button
          type="button"
          onClick={function () {
            router.push("/workflow/tracker");
          }}
          className="mt-4 flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-200"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back to Tracker
        </button>
      </div>
    </div>
  );
}
