"use client";

import React, { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

type KpiStatus = "On Track" | "Achieved" | "At Risk";

interface Kpi {
  id: string;
  department: string;
  metric: string;
  target: string;
  current: string;
  progressPercent: number;
  owner: string;
  status: KpiStatus;
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

const INITIAL_KPIS: Kpi[] = [
  { id: makeId(), department: "Engineering", metric: "Code Review Turnaround", target: "<6hrs", current: "5.2hrs", progressPercent: 78, owner: "Ngozi A.", status: "On Track" },
  { id: makeId(), department: "Engineering", metric: "Sprint Velocity", target: ">40pts", current: "42pts", progressPercent: 100, owner: "Chidi O.", status: "Achieved" },
  { id: makeId(), department: "Engineering", metric: "Bug Resolution Time", target: "<48hrs", current: "54hrs", progressPercent: 60, owner: "Yusuf I.", status: "At Risk" },
  { id: makeId(), department: "Engineering", metric: "Test Coverage", target: ">80%", current: "78%", progressPercent: 90, owner: "Kemi A.", status: "On Track" },
  { id: makeId(), department: "Engineering", metric: "Deployment Frequency", target: "Daily", current: "0.8/day", progressPercent: 70, owner: "Amara E.", status: "On Track" },
  { id: makeId(), department: "Engineering", metric: "Customer Satisfaction Score", target: ">4.5", current: "4.7", progressPercent: 100, owner: "Emeka N.", status: "Achieved" },
  { id: makeId(), department: "Sales & Marketing", metric: "Lead Conversion Rate", target: ">25%", current: "28%", progressPercent: 100, owner: "Tolu B.", status: "Achieved" },
  { id: makeId(), department: "Sales & Marketing", metric: "Revenue per Rep", target: ">N15M", current: "N12.8M", progressPercent: 65, owner: "Bola K.", status: "On Track" },
  { id: makeId(), department: "Human Resources", metric: "Onboarding Time", target: "<3 days", current: "2.1 days", progressPercent: 100, owner: "Funke M.", status: "Achieved" },
  { id: makeId(), department: "Human Resources", metric: "Retention Rate", target: ">90%", current: "87%", progressPercent: 87, owner: "Aisha D.", status: "On Track" },
];

function statusClasses(status: KpiStatus) {
  if (status === "Achieved") {
    return "bg-emerald-500/15 text-emerald-400";
  }
  if (status === "At Risk") {
    return "bg-amber-500/15 text-amber-400";
  }
  return "bg-indigo-500/15 text-indigo-300";
}

function barClasses(status: KpiStatus) {
  if (status === "Achieved") {
    return "bg-emerald-500";
  }
  if (status === "At Risk") {
    return "bg-amber-500";
  }
  return "bg-indigo-500";
}

function groupByDepartment(kpis: Kpi[]) {
  const groups: { department: string; items: Kpi[] }[] = [];
  kpis.forEach(function (kpi) {
    const existing = groups.find(function (g) {
      return g.department === kpi.department;
    });
    if (existing) {
      existing.items.push(kpi);
    } else {
      groups.push({ department: kpi.department, items: [kpi] });
    }
  });
  return groups;
}

export default function KpisPage() {
  const router = useRouter();
  const [kpis, setKpis] = useState<Kpi[]>(INITIAL_KPIS);

  function addKpi() {
    const metric = window.prompt("KPI metric name:");
    if (!metric || !metric.trim()) {
      return;
    }
    const department = window.prompt("Department:", "Engineering") || "Engineering";
    const target = window.prompt("Target:", "") || "";
    const owner = window.prompt("Owner:", "") || "";

    setKpis([
      ...kpis,
      {
        id: makeId(),
        department: department,
        metric: metric.trim(),
        target: target,
        current: "0",
        progressPercent: 0,
        owner: owner,
        status: "On Track",
      },
    ]);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // TODO: replace with a real call to the Performance module endpoint
    // once the backend is ready.
    console.log("KPIs submitted:", kpis);
    router.push("/onboarding/invite-team");
  }

  const grouped = groupByDepartment(kpis);

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

            if (i < 4) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else if (i === 4) {
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

      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Assign departmental KPIs</h1>
          <p className="mt-2 text-gray-400">
            Set performance metrics for each department based on AI-identified critical roles.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Departmental KPIs</h2>
            <span className="text-sm text-gray-500">Assign measurable targets to each department</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="pb-3 pr-4 font-medium">KPI Metric</th>
                  <th className="pb-3 pr-4 font-medium">Target</th>
                  <th className="pb-3 pr-4 font-medium">Current</th>
                  <th className="pb-3 pr-4 font-medium">Progress</th>
                  <th className="pb-3 pr-4 font-medium">Owner</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map(function (group) {
                  return (
                    <React.Fragment key={group.department}>
                      <tr>
                        <td colSpan={6} className="pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-indigo-400">
                          {group.department}
                        </td>
                      </tr>
                      {group.items.map(function (kpi) {
                        return (
                          <tr key={kpi.id} className="border-b border-white/5">
                            <td className="py-3 pr-4 font-medium">{kpi.metric}</td>
                            <td className="py-3 pr-4 text-gray-400">{kpi.target}</td>
                            <td className="py-3 pr-4 font-semibold">{kpi.current}</td>
                            <td className="py-3 pr-4">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
                                  <div
                                    className={"h-full rounded-full " + barClasses(kpi.status)}
                                    style={{ width: kpi.progressPercent + "%" }}
                                  />
                                </div>
                              </div>
                            </td>
                            <td className="py-3 pr-4 text-gray-400">{kpi.owner}</td>
                            <td className="py-3">
                              <span className={"rounded-full px-3 py-1 text-xs font-medium " + statusClasses(kpi.status)}>
                                {kpi.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          <button
            type="button"
            onClick={addKpi}
            className="w-full rounded-lg border border-dashed border-indigo-500/40 py-3 text-sm font-medium text-indigo-400 hover:border-indigo-500/70"
          >
            + Assign Departmental KPI
          </button>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/ai-suggestions");
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
