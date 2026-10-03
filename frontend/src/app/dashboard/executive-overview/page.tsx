"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface DepartmentRow {
  id: string;
  name: string;
  headcount: number;
  attendancePercent: number;
  kpiScore: number;
  route: string;
}

const DEPARTMENTS: DepartmentRow[] = [
  { id: "engineering", name: "Engineering", headcount: 84, attendancePercent: 94.5, kpiScore: 84, route: "/dashboard/departments/engineering" },
  { id: "hr", name: "HR", headcount: 18, attendancePercent: 91.2, kpiScore: 79, route: "/dashboard/departments/engineering" },
  { id: "sales", name: "Sales", headcount: 62, attendancePercent: 89.8, kpiScore: 75, route: "/dashboard/departments/engineering" },
  { id: "finance", name: "Finance", headcount: 14, attendancePercent: 93.1, kpiScore: 81, route: "/dashboard/departments/engineering" },
  { id: "operations", name: "Operations", headcount: 72, attendancePercent: 92.4, kpiScore: 78, route: "/dashboard/departments/engineering" },
  { id: "customer-success", name: "Customer Success", headcount: 34, attendancePercent: 91.6, kpiScore: 72, route: "/dashboard/departments/engineering" },
];

const PERIOD_OPTIONS = ["Q1 2026", "Q2 2026", "Q3 2026", "Q4 2026"];

function scoreBarColor(score: number) {
  if (score >= 82) {
    return "bg-emerald-500";
  }
  return "bg-indigo-500";
}

function SidebarNav() {
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
        <a href="#" className="rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-medium text-white">
          Dashboard
        </a>
        <a href="#" className="rounded-lg px-3 py-2.5 text-sm text-gray-400 hover:bg-white/5">
          Strategy &amp; Performance
        </a>
        <a href="#" className="rounded-lg px-3 py-2.5 text-sm text-gray-400 hover:bg-white/5">
          Reports
        </a>
        <a href="#" className="rounded-lg px-3 py-2.5 text-sm text-gray-400 hover:bg-white/5">
          Settings
        </a>
      </nav>
    </div>
  );
}

function DonutChart() {
  // Engineering 30%, HR 6%, Sales 22%, remaining 42% split across others
  const segments = [
    { color: "#6366f1", percent: 30 },
    { color: "#34d399", percent: 6 },
    { color: "#f59e0b", percent: 22 },
    { color: "#4b5563", percent: 42 },
  ];
  let cumulative = 0;
  const gradientParts = segments.map(function (seg) {
    const start = cumulative;
    cumulative += seg.percent;
    return seg.color + " " + start + "% " + cumulative + "%";
  });
  const gradient = "conic-gradient(" + gradientParts.join(", ") + ")";

  return (
    <div
      className="relative flex h-36 w-36 items-center justify-center rounded-full"
      style={{ background: gradient }}
    >
      <div className="flex h-24 w-24 flex-col items-center justify-center rounded-full bg-[#0d1220]">
        <span className="text-2xl font-bold">284</span>
        <span className="text-xs text-gray-500">FTEs</span>
      </div>
    </div>
  );
}

function LineChart({ points, color }: { points: number[]; color: string }) {
  const width = 220;
  const height = 60;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);

  const coords = points.map(function (p, i) {
    const x = i * stepX;
    const y = height - ((p - min) / range) * height;
    return x + "," + y;
  });

  return (
    <svg width={width} height={height} viewBox={"0 0 " + width + " " + height}>
      <polyline points={coords.join(" ")} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  );
}

export default function ExecutiveOverviewPage() {
  const router = useRouter();
  const [period, setPeriod] = useState("Q3 2026");

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />
      <div className="flex-1 px-8 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Executive Overview</h1>
            <p className="text-sm text-gray-500">System Status &middot; Corporate Performance OS Dashboard</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={period}
              onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                setPeriod(e.target.value);
              }}
              className="rounded-lg border border-white/10 bg-[#0d1220] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
            >
              {PERIOD_OPTIONS.map(function (opt) {
                return (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                );
              })}
            </select>
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#0d1220] text-gray-300 hover:bg-white/5"
              aria-label="Notifications"
              onClick={function () {
                router.push("/notifications");
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-400">
              WOS MVP Ready
            </span>
          </div>
        </div>

        {/* Stat cards */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Total Workforce</p>
            <p className="mt-2 text-2xl font-bold">284</p>
            <p className="mt-1 flex items-center gap-1 text-xs text-emerald-400">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
              +12 new onboardings this month
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Overall Attendance</p>
            <p className="mt-2 text-2xl font-bold">92.1%</p>
            <p className="mt-1 flex items-center gap-1 text-xs text-emerald-400">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
              +1.8% system performance baseline
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">KPI Achievement</p>
            <p className="mt-2 text-2xl font-bold">76%</p>
            <p className="mt-1 text-xs text-gray-500">Avg weighted target standard</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Open Positions</p>
            <p className="mt-2 text-2xl font-bold">12</p>
            <p className="mt-1 text-xs text-gray-500">Active recruitment pipeline status</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">Turnover Rate</p>
            <p className="mt-2 text-2xl font-bold">4.2%</p>
            <p className="mt-1 flex items-center gap-1 text-xs text-red-400">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M12 5v14M5 12l7 7 7-7" />
              </svg>
              -0.8% continuous health index
            </p>
          </div>
        </div>

        {/* Departmental Operational Breakdown */}
        <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <h2 className="text-base font-semibold">Departmental Operational Breakdown</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[600px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="pb-2 pr-4 font-medium">Department</th>
                  <th className="pb-2 pr-4 font-medium">Headcount</th>
                  <th className="pb-2 pr-4 font-medium">Attendance %</th>
                  <th className="pb-2 font-medium">KPI Score / Status Performance</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {DEPARTMENTS.map(function (dept: DepartmentRow) {
                  return (
                    <tr
                      key={dept.id}
                      onClick={function () {
                        router.push(dept.route);
                      }}
                      className="cursor-pointer border-b border-white/5 hover:bg-white/5"
                    >
                      <td className="py-3 pr-4 font-medium">{dept.name}</td>
                      <td className="py-3 pr-4 text-gray-400">{dept.headcount}</td>
                      <td className="py-3 pr-4 text-gray-400">{dept.attendancePercent}%</td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <span className="w-9 text-xs font-semibold">{dept.kpiScore}%</span>
                          <div className="h-1.5 w-32 overflow-hidden rounded-full bg-white/10">
                            <div
                              className={"h-full rounded-full " + scoreBarColor(dept.kpiScore)}
                              style={{ width: dept.kpiScore + "%" }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="py-3 text-right text-gray-600">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="ml-auto">
                          <path d="M9 18l6-6-6-6" />
                        </svg>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Workforce Health + Trend Overview */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <h2 className="text-base font-semibold">Workforce Health</h2>
            <div className="mt-4 flex items-center gap-6">
              <DonutChart />
              <div className="space-y-2 text-sm">
                <p className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-indigo-500" /> Engineering (30%)
                </p>
                <p className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" /> HR (6%)
                </p>
                <p className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-amber-500" /> Sales (22%)
                </p>
              </div>
            </div>
            <p className="mt-4 text-xs text-gray-500">6-Month Headcount Growth</p>
            <div className="mt-1">
              <LineChart points={[240, 252, 261, 268, 275, 284]} color="#818cf8" />
            </div>
            <p className="mt-1 text-sm font-semibold">284 Active</p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
            <h2 className="text-base font-semibold">Trend Overview</h2>
            <div className="mt-4 space-y-6">
              <div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>Overall Attendance Trend</span>
                  <span className="font-semibold text-white">92.1%</span>
                </div>
                <LineChart points={[89, 90, 91.5, 90.8, 92.1, 92.1]} color="#818cf8" />
                <div className="flex justify-between text-xs text-gray-600">
                  <span>Jul</span>
                  <span>Sep</span>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>Weighted KPI Achievement</span>
                  <span className="font-semibold text-white">76.0%</span>
                </div>
                <LineChart points={[68, 70, 74, 72, 75, 76]} color="#34d399" />
                <div className="flex justify-between text-xs text-gray-600">
                  <span>Jul</span>
                  <span>Sep</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
