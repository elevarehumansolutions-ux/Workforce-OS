"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

type Category = "Operational" | "Revenue" | "Vacancy Risk";
type RiskLevel = "High" | "Medium" | "Low";
type RoleStatus = "pending" | "approved" | "rejected";

interface SuggestedRole {
  id: string;
  title: string;
  department: string;
  rationale: string;
  category: Category;
  riskLevel: RiskLevel;
  revenueAllocationPercent: number | null;
  status: RoleStatus;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

const INITIAL_ROLES: SuggestedRole[] = [
  {
    id: makeId(),
    title: "Chief Technology Officer",
    department: "Engineering",
    rationale: "Sole executive overseeing all technical infrastructure",
    category: "Operational",
    riskLevel: "High",
    revenueAllocationPercent: null,
    status: "pending",
  },
  {
    id: makeId(),
    title: "Head of Sales",
    department: "Sales & Marketing",
    rationale: "No identified successor in reporting chain",
    category: "Revenue",
    riskLevel: "High",
    revenueAllocationPercent: 22,
    status: "pending",
  },
  {
    id: makeId(),
    title: "Lead Cloud Architect",
    department: "Engineering",
    rationale: "Sole role with system-wide deployment access",
    category: "Operational",
    riskLevel: "Medium",
    revenueAllocationPercent: null,
    status: "pending",
  },
  {
    id: makeId(),
    title: "Finance Controller",
    department: "Finance",
    rationale: "Key signatory on all vendor contracts",
    category: "Revenue",
    riskLevel: "Low",
    revenueAllocationPercent: 12,
    status: "pending",
  },
  {
    id: makeId(),
    title: "HR Business Partner",
    department: "Human Resources",
    rationale: "Only HR liaison across 3 departments",
    category: "Vacancy Risk",
    riskLevel: "Medium",
    revenueAllocationPercent: null,
    status: "pending",
  },
];

function categoryClasses(category: Category) {
  if (category === "Revenue") {
    return "bg-indigo-500/15 text-indigo-300";
  }
  if (category === "Operational") {
    return "bg-cyan-500/15 text-cyan-300";
  }
  return "bg-amber-500/15 text-amber-300";
}

function riskClasses(risk: RiskLevel) {
  if (risk === "High") {
    return "bg-red-500/15 text-red-400";
  }
  if (risk === "Medium") {
    return "bg-amber-500/15 text-amber-400";
  }
  return "bg-emerald-500/15 text-emerald-400";
}

export default function AiSuggestionsPage() {
  const router = useRouter();
  const [roles, setRoles] = useState<SuggestedRole[]>(INITIAL_ROLES);

  function setStatus(id: string, status: RoleStatus) {
    setRoles(
      roles.map(function (role: SuggestedRole) {
        if (role.id === id) {
          return { ...role, status: status };
        }
        return role;
      })
    );
  }

  function approveAll() {
    setRoles(
      roles.map(function (role: SuggestedRole) {
        return { ...role, status: "approved" as RoleStatus };
      })
    );
  }

  function editRole(id: string) {
    const role = roles.find(function (r: SuggestedRole) {
      return r.id === id;
    });
    if (!role) {
      return;
    }
    const newTitle = window.prompt("Edit role title:", role.title);
    if (newTitle && newTitle.trim()) {
      setRoles(
        roles.map(function (r: SuggestedRole) {
          if (r.id === id) {
            return { ...r, title: newTitle.trim() };
          }
          return r;
        })
      );
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // TODO: replace with a real call to the Critical Roles module endpoint
    // once the backend is ready. Revenue allocation percentages here feed
    // scoring and dashboards only, they are not connected to payroll.
    console.log("Critical roles submitted:", roles);
    router.push("/onboarding/kpis");
  }

  const pendingCount = roles.filter(function (r: SuggestedRole) {
    return r.status === "pending";
  }).length;

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="flex items-center justify-between border-b border-white/10 px-8 py-4 sm:px-12">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <circle cx="9" cy="8" r="3" />
              <path d="M2 20c0-3 3-5 7-5s7 2 7 5" />
              <circle cx="17" cy="8" r="2.5" />
              <path d="M22 20c0-2.5-2-4-4.5-4.5" />
            </svg>
          </div>
          <span className="text-base font-bold">Elevare</span>
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {ONBOARDING_STEPS.map(function (step, i) {
            let circleClass = "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ";
            let labelClass = "text-sm ";
            let isCheck = false;

            if (i < 3) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else if (i === 3) {
              circleClass += "bg-indigo-500 text-white";
              labelClass += "font-medium text-indigo-400";
            } else {
              circleClass += "border border-white/20 text-gray-400";
              labelClass += "text-gray-500";
            }

            return (
              <div key={step} className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <span className={circleClass}>
                    {isCheck ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    ) : (
                      i + 1
                    )}
                  </span>
                  <span className={labelClass}>{step}</span>
                </div>
                {i < ONBOARDING_STEPS.length - 1 && <span className="h-px w-6 bg-white/10" />}
              </div>
            );
          })}
        </div>

        <div className="text-sm text-gray-400">
          Need help? <a href="#" className="text-indigo-400 hover:text-indigo-300">Contact Support</a>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Review AI-suggested critical roles</h1>
          <p className="mt-2 text-gray-400">
            Our AI has analyzed your organization structure and identified roles critical to operations
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                AI Engine Active
              </span>
              <span className="text-sm text-gray-300">{pendingCount} roles flagged for review</span>
            </div>
            <button
              type="button"
              onClick={approveAll}
              className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
            >
              Approve All
            </button>
          </div>

          <div className="space-y-4">
            {roles.map(function (role: SuggestedRole) {
              const isDecided = role.status !== "pending";
              return (
                <div
                  key={role.id}
                  className={
                    "rounded-2xl border p-5 shadow-xl backdrop-blur-sm " +
                    (isDecided
                      ? "border-white/5 bg-[#0d1220]/40 opacity-60"
                      : "border-white/10 bg-[#0d1220]/80")
                  }
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold">{role.title}</h3>
                        <span className="text-sm text-gray-500">• {role.department}</span>
                        <span className="rounded bg-white/10 px-2 py-0.5 text-xs font-medium text-gray-300">
                          AI SUGGESTED
                        </span>
                        {role.status !== "pending" && (
                          <span
                            className={
                              "rounded px-2 py-0.5 text-xs font-medium " +
                              (role.status === "approved"
                                ? "bg-emerald-500/15 text-emerald-400"
                                : "bg-red-500/15 text-red-400")
                            }
                          >
                            {role.status === "approved" ? "APPROVED" : "REJECTED"}
                          </span>
                        )}
                      </div>

                      <p className="mt-2 text-sm text-gray-400">
                        <span className="italic text-gray-500">AI Rationale:</span> {role.rationale}
                      </p>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <span className={"rounded px-2 py-1 text-xs font-medium " + categoryClasses(role.category)}>
                          {role.category}
                        </span>
                        <span className={"rounded px-2 py-1 text-xs font-medium " + riskClasses(role.riskLevel)}>
                          {role.riskLevel}
                        </span>
                        {role.revenueAllocationPercent !== null && (
                          <span className="text-xs text-gray-500">
                            Revenue allocation: {role.revenueAllocationPercent}% (scoring and dashboards only)
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-shrink-0 items-center gap-2">
                      <button
                        type="button"
                        disabled={isDecided}
                        onClick={function () {
                          setStatus(role.id, "approved");
                        }}
                        className="rounded-lg border border-emerald-500/40 px-4 py-2 text-sm font-medium text-emerald-400 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={isDecided}
                        onClick={function () {
                          editRole(role.id);
                        }}
                        className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={isDecided}
                        onClick={function () {
                          setStatus(role.id, "rejected");
                        }}
                        className="rounded-lg border border-red-500/40 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/okrs");
              }}
              className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-200"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Go Back
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Save & Continue
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
